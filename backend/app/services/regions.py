from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.errors import AppError
from app.core.storage import resolve_within
from app.db.project_schema import project_db
from app.services import artwork as artwork_service
from app.services import equation_latex
from app.services import image_edits as edits_service
from app.services import ocr as ocr_service
from app.services import pdf as pdf_service

# A figure suggestion is anchored to a figure-like caption, to artwork the page
# itself exposes (an embedded PDF image or vector drawing), or, on a photographed
# page, to large ink clusters that the OCR text layout does not explain. Without
# one of those signals there is no reliable local evidence that separates a
# drawing from empty space, so the region is left to manual selection.
FIGURE_CAPTION_RE = re.compile(
    r"^(?:figure|fig\.?|diagram|chart|plate|photo|image|illustration)\b",
    re.IGNORECASE,
)
MARGIN_KINDS = frozenset({"header", "footer", "page_number"})
MERGEABLE_KINDS = ("table", "equation")
MAX_PROPOSALS = 20
PADDING_RATIO = 0.008
FIGURE_GAP_RATIO = 0.06
DEDUPE_IOU = 0.85
# A raster image or a drawing covering almost the whole page is usually a
# scanned background or a page frame. Very small ones are usually logos, rules
# or bullets.
BACKGROUND_SHARE = 0.8
IMAGE_MIN_WIDTH_RATIO = 0.05
IMAGE_MIN_HEIGHT_RATIO = 0.03
# A drawing has no caption of its own to prove it is artwork, so it has to be
# large enough to be worth reading before it becomes a suggestion.
DRAWING_MIN_WIDTH_RATIO = 0.08
DRAWING_MIN_HEIGHT_RATIO = 0.04

Rect = dict[str, float]


def _get_page(conn, page_id: str):
    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if row is None:
        raise AppError(404, "page_not_found", "Page not found.")
    return row


def _block_dict(row) -> dict[str, Any] | None:
    values = (row["x"], row["y"], row["width"], row["height"])
    if any(value is None for value in values):
        return None
    x, y, width, height = (float(value) for value in values)
    if width <= 0 or height <= 0:
        return None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "text": row["text"] or "",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
    }


def _row_words(row) -> list[dict[str, Any]]:
    """Read the stored word boxes for one block, tolerating older rows."""
    try:
        raw = row["words"]
    except (IndexError, KeyError):
        return []
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _right(block: dict[str, Any]) -> float:
    return block["x"] + block["width"]


def _bottom(block: dict[str, Any]) -> float:
    return block["y"] + block["height"]


def _overlap_width(first: dict[str, Any], second: dict[str, Any]) -> float:
    return min(_right(first), _right(second)) - max(first["x"], second["x"])


def _horizontal_overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return _overlap_width(first, second) > 0


def _union(blocks: list[dict[str, Any]]) -> Rect:
    left = min(block["x"] for block in blocks)
    top = min(block["y"] for block in blocks)
    right = max(_right(block) for block in blocks)
    bottom = max(_bottom(block) for block in blocks)
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def _intersection(first: Rect, second: Rect) -> float:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["width"], second["x"] + second["width"])
    bottom = min(first["y"] + first["height"], second["y"] + second["height"])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def iou(first: Rect, second: Rect) -> float:
    intersection = _intersection(first, second)
    if intersection <= 0:
        return 0.0
    union = (
        first["width"] * first["height"]
        + second["width"] * second["height"]
        - intersection
    )
    return intersection / union if union > 0 else 0.0


def _cluster(blocks: list[dict[str, Any]], gap_ratio: float) -> list[Rect]:
    """Group blocks of one kind that read as a single region.

    Tesseract usually keeps a table or an equation in one block, but a wide
    table can split into several. Vertical neighbours are merged only when
    their columns overlap and the gap stays small relative to their height.
    """
    clusters: list[list[dict[str, Any]]] = []
    for block in sorted(blocks, key=lambda item: (item["y"], item["x"])):
        target: list[dict[str, Any]] | None = None
        for cluster in clusters:
            current = _union(cluster)
            gap = block["y"] - (current["y"] + current["height"])
            tallest = max(current["height"], block["height"])
            if gap > max(4.0, gap_ratio * tallest):
                continue
            if gap < -0.25 * min(current["height"], block["height"]):
                continue
            if _overlap_width(current, block) <= 0:
                continue
            share = _overlap_width(current, block) / min(current["width"], block["width"])
            if share < 0.25:
                continue
            target = cluster
            break
        if target is None:
            clusters.append([block])
        else:
            target.append(block)
    return [_union(cluster) for cluster in clusters]


def clamp_rect(
    rect: Rect, page_width: int, page_height: int
) -> dict[str, int] | None:
    pad_x = max(2, round(page_width * PADDING_RATIO))
    pad_y = max(2, round(page_height * PADDING_RATIO))
    left = max(0, int(round(rect["x"])) - pad_x)
    top = max(0, int(round(rect["y"])) - pad_y)
    right = min(page_width, int(round(rect["x"] + rect["width"])) + pad_x)
    bottom = min(page_height, int(round(rect["y"] + rect["height"])) + pad_y)
    width = right - left
    height = bottom - top
    if width < 8 or height < 8:
        return None
    return {"x": left, "y": top, "width": width, "height": height}


def _content_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in blocks if block["kind"] not in MARGIN_KINDS]


def _column_bounds(
    caption: dict[str, Any], blocks: list[dict[str, Any]]
) -> tuple[float, float]:
    overlapping = [
        block
        for block in _content_blocks(blocks)
        if block is not caption and _horizontal_overlap(block, caption)
    ]
    left = min([caption["x"], *(block["x"] for block in overlapping)])
    right = max([_right(caption), *(_right(block) for block in overlapping)])
    return left, right


def _figure_rects(
    blocks: list[dict[str, Any]], page_width: int, page_height: int
) -> list[tuple[Rect, dict[str, Any]]]:
    """Suggest the empty band above a figure caption.

    Captions conventionally sit below the artwork. The band is limited to the
    caption's column, ends at the nearest text above and is only proposed when
    it is tall enough to hold artwork. Everything the user sees is a proposal:
    no crop is created until the user confirms it.
    """
    content = _content_blocks(blocks)
    captions = [
        block
        for block in content
        if block["kind"] == "caption"
        and FIGURE_CAPTION_RE.match(block["text"].strip())
    ]
    minimum_gap = max(24.0, page_height * FIGURE_GAP_RATIO)
    margin = max(2.0, page_height * 0.005)
    results: list[tuple[Rect, dict[str, Any]]] = []
    for caption in captions:
        above = [
            block
            for block in content
            if block is not caption
            and _horizontal_overlap(block, caption)
            and _bottom(block) <= caption["y"] + 1
        ]
        band_top = (
            max((_bottom(block) for block in above), default=page_height * 0.05)
        )
        if caption["y"] - band_top < minimum_gap:
            continue
        left, right = _column_bounds(caption, blocks)
        top = band_top + margin
        bottom = caption["y"] - margin
        if bottom - top < 8 or right - left < 8:
            continue
        results.append(
            (
                {
                    "x": left,
                    "y": top,
                    "width": right - left,
                    "height": bottom - top,
                },
                caption,
            )
        )
    # Several captions inside one figure band would propose the same area.
    unique: list[tuple[Rect, dict[str, Any]]] = []
    for rect, caption in sorted(results, key=lambda item: item[0]["y"]):
        if any(iou(rect, kept[0]) >= DEDUPE_IOU for kept in unique):
            continue
        unique.append((rect, caption))
    return unique


def _image_rects(
    rects: list[Rect], page_width: int, page_height: int
) -> list[Rect]:
    """Keep embedded-image boxes that could plausibly be a figure.

    A full-page raster is normally a scanned background, and a very small image
    is normally a logo or a rule. Both are skipped so the suggestion list stays
    about content the user may actually want to crop.
    """
    minimum_width = max(8.0, page_width * IMAGE_MIN_WIDTH_RATIO)
    minimum_height = max(8.0, page_height * IMAGE_MIN_HEIGHT_RATIO)
    return _plausible(rects, minimum_width, minimum_height, page_width, page_height)


def _drawing_rects(
    rects: list[Rect], page_width: int, page_height: int
) -> list[Rect]:
    """Keep vector drawings large enough to be a figure.

    The drawing has already been separated from table rules by the PDF layer.
    Size is the remaining filter: a small drawing is decoration, while a
    page-sized one is usually a frame or a background.
    """
    minimum_width = max(8.0, page_width * DRAWING_MIN_WIDTH_RATIO)
    minimum_height = max(8.0, page_height * DRAWING_MIN_HEIGHT_RATIO)
    return _plausible(rects, minimum_width, minimum_height, page_width, page_height)


def _plausible(
    rects: list[Rect],
    minimum_width: float,
    minimum_height: float,
    page_width: int,
    page_height: int,
) -> list[Rect]:
    kept: list[Rect] = []
    for rect in rects:
        if rect["width"] < minimum_width or rect["height"] < minimum_height:
            continue
        if (
            rect["width"] >= page_width * BACKGROUND_SHARE
            and rect["height"] >= page_height * BACKGROUND_SHARE
        ):
            continue
        kept.append(rect)
    return kept


def _same_area(first: Rect, second: Rect) -> bool:
    """True when two boxes describe the same artwork.

    A caption band is usually a little wider than the artwork, so the overlap is
    compared with the smaller box instead of requiring an exact match. Both
    boxes remain proposals: merging only decides which rectangle and caption
    the user sees.
    """
    intersection = _intersection(first, second)
    if intersection <= 0:
        return False
    smaller = min(
        first["width"] * first["height"],
        second["width"] * second["height"],
    )
    return smaller > 0 and intersection / smaller >= 0.6


def _caption_band_matches(artwork: Rect, band: Rect) -> bool:
    """True when a caption band describes the same artwork box.

    The band is an estimate built from the caption and the text above it, so it
    can be narrower or shifted relative to the real artwork. Comparing area
    alone then under-matches a wide image under a short caption and offers the
    user two boxes for one figure. The band and the artwork must instead share
    most of the smaller box on both axes.
    """
    left = max(artwork["x"], band["x"])
    top = max(artwork["y"], band["y"])
    right = min(artwork["x"] + artwork["width"], band["x"] + band["width"])
    bottom = min(artwork["y"] + artwork["height"], band["y"] + band["height"])
    if right <= left or bottom <= top:
        return False
    smaller_width = min(artwork["width"], band["width"])
    smaller_height = min(artwork["height"], band["height"])
    if smaller_width <= 0 or smaller_height <= 0:
        return False
    return (
        (right - left) / smaller_width >= 0.5
        and (bottom - top) / smaller_height >= 0.5
    )


def _inside(rect: Rect, container: Rect) -> bool:
    """True when most of ``rect`` lies inside ``container``."""
    area = rect["width"] * rect["height"]
    if area <= 0:
        return False
    return _intersection(rect, container) / area >= 0.6


def _drawing_figures(
    drawings: list[Rect], images: list[Rect], excluded: list[Rect]
) -> list[Rect]:
    """Keep drawings that describe artwork no other signal already covers.

    A filled frame or a shaded band can sit behind an embedded image or inside a
    detected table. Those regions already have a proposal, so the drawing is
    dropped instead of offering the user the same area twice.
    """
    kept: list[Rect] = []
    for rect in drawings:
        if any(
            _same_area(rect, other) or iou(rect, other) >= DEDUPE_IOU
            for other in images
        ):
            continue
        if any(_inside(rect, other) for other in excluded):
            continue
        if any(iou(rect, other) >= DEDUPE_IOU for other in kept):
            continue
        kept.append(rect)
    return kept


def already_extracted(proposal: Rect, element: Rect) -> bool:
    """Treat a proposal as covered when an element holds almost all of it.

    The proposal is padded around the OCR geometry, so an exact user crop and
    the proposal rarely share an IoU of 1. Requiring both a high element
    coverage and a meaningful IoU keeps small elements inside a larger
    suggested region from hiding that larger proposal.
    """
    intersection = _intersection(proposal, element)
    if intersection <= 0:
        return False
    area = element["width"] * element["height"]
    if area <= 0:
        return False
    return intersection / area >= 0.9 and iou(proposal, element) >= 0.5


def _proposal(
    rect: dict[str, int],
    *,
    kind: str,
    reason: str,
    confidence: str,
    caption: str = "",
    block_ids: list[str],
) -> dict[str, Any]:
    return {
        "key": f"{kind}-{rect['x']}-{rect['y']}-{rect['width']}-{rect['height']}",
        "kind": kind,
        "x": rect["x"],
        "y": rect["y"],
        "width": rect["width"],
        "height": rect["height"],
        "caption": caption,
        "reason": reason,
        "confidence": confidence,
        "block_ids": block_ids,
    }


def _empty(
    status: str,
    run,
    page_width: int | None,
    page_height: int | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "page_width": page_width,
        "page_height": page_height,
        "ocr_run_id": run["id"] if run is not None else None,
        "engine": run["engine"] if run is not None else None,
        "proposals": [],
    }


def assemble_figures(
    page_width: int,
    page_height: int,
    blocks: list[dict[str, Any]],
    image_rects: list[Rect],
    drawing_rects: list[Rect],
    raster_rects: list[Rect],
    text_regions: list[Rect],
) -> list[dict[str, Any]]:
    """Combine artwork evidence into reviewable figure candidates.

    An embedded image gives the precise artwork box. A caption band gives the
    text but only approximates the artwork, so when both describe the same area
    the image rectangle is kept and the caption is attached to it. A caption
    without matching artwork still becomes its own suggestion. Raster ink is
    dropped when it sits inside a table or equation the OCR layout already
    explains, and vector drawings are dropped when an image or a table already
    covers the same area. Nothing here is persisted or accepted: the caller
    exposes the boxes for review.
    """
    figures: list[dict[str, Any]] = [
        {
            "rect": rect,
            "caption": "",
            "reason": "pdf_image_region",
            "confidence": "medium",
            "block_ids": [],
        }
        for rect in image_rects
    ]
    # Ink outside the OCR text blocks is the only local signal left on a
    # photographed page. It is weaker than PDF geometry: a ruled table the engine
    # did not read as a table, or a header, can look like artwork. The region is
    # therefore offered as a low-confidence figure and never saved on its own.
    for rect in raster_rects:
        if any(_inside(rect, proposal) for proposal in text_regions):
            continue
        figures.append(
            {
                "rect": rect,
                "caption": "",
                "reason": "page_artwork_region",
                "confidence": "low",
                "block_ids": [],
            }
        )
    # A drawing is a weaker signal than an image: it may be shading or a border
    # around content that is already proposed. It is only kept when it is not
    # the same area as an image and does not sit inside a detected table, which
    # is where cell shading and rules usually appear.
    for rect in _drawing_figures(drawing_rects, image_rects, text_regions):
        figures.append(
            {
                "rect": rect,
                "caption": "",
                "reason": "pdf_drawing_region",
                "confidence": "medium",
                "block_ids": [],
            }
        )
    for rect, caption in _figure_rects(blocks, page_width, page_height):
        caption_text = caption["text"].strip()[:500]
        matched = next(
            (
                candidate
                for candidate in figures
                if _same_area(candidate["rect"], rect)
                or _caption_band_matches(candidate["rect"], rect)
            ),
            None,
        )
        if matched is not None:
            if not matched["caption"]:
                matched["caption"] = caption_text
                matched["block_ids"] = [caption["id"]]
            continue
        figures.append(
            {
                "rect": rect,
                "caption": caption_text,
                "reason": "figure_caption_gap",
                "confidence": "medium",
                "block_ids": [caption["id"]],
            }
        )
    return figures


def propose_regions(project_dir: Path, page_id: str) -> dict[str, Any]:
    """Derive reviewable region proposals from local layout evidence.

    Text comes from the latest OCR run. PDF pages also expose the placement of
    embedded raster images and the shapes of vector drawings, which are
    deterministic signals that a region contains artwork even without a caption.
    On a photographed page, large ink clusters outside the OCR text blocks are the
    remaining local signal and are offered as low-confidence figures. The same
    raster signal is used on a PDF page when its artwork is opaque: no readable
    embedded image and no vector rectangle, for example a scanned page or artwork
    stored as form content. Proposals are not persisted and never become elements
    on their own: the user reviews the rectangle and caption, then saves it through
    the normal crop path, so a bad suggestion costs nothing and is never treated as
    verified content.
    """
    ocr_service.recover_active_runs(project_dir, page_id)
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        page_width = page["width"]
        page_height = page["height"]
        run = conn.execute(
            "SELECT * FROM ocr_runs WHERE page_id = ? ORDER BY created_at DESC LIMIT 1",
            (page_id,),
        ).fetchone()
        blocks: list[dict[str, Any]] = []
        if run is not None:
            rows = conn.execute(
                "SELECT * FROM ocr_blocks WHERE run_id = ? ORDER BY block_index ASC",
                (run["id"],),
            ).fetchall()
            blocks = [block for row in rows if (block := _block_dict(row)) is not None]
        existing = [
            {
                "x": float(row["x"]),
                "y": float(row["y"]),
                "width": float(row["width"]),
                "height": float(row["height"]),
            }
            for row in conn.execute(
                "SELECT x, y, width, height FROM elements WHERE page_id = ?",
                (page_id,),
            ).fetchall()
        ]
        # Embedded raster images and vector drawings are deterministic local
        # evidence that a region contains artwork. Both are only read from the
        # immutable PDF, so page rotation or a geometry edit makes the boxes
        # unusable.
        pdf_source: tuple[Path, int] | None = None
        if page["source_kind"] == "pdf" and int(page["rotation"]) == 0:
            if not edits_service.has_edits(edits_service.decode_edits(page["edits"])):
                asset = conn.execute(
                    "SELECT relative_path FROM assets WHERE id = ?",
                    (page["original_asset_id"],),
                ).fetchone()
                if asset is not None:
                    try:
                        pdf_path = resolve_within(project_dir, asset["relative_path"])
                    except ValueError:
                        pdf_path = None
                    if pdf_path is not None and pdf_path.exists():
                        pdf_source = (
                            pdf_path,
                            max(0, int(page["pdf_page_number"] or 1) - 1),
                        )
        # A photographed page has no PDF layer, so its current render is read.
        # A PDF page also keeps a rendered display asset; it is the only signal
        # left when the artwork is stored as opaque page/form content with no
        # readable embedded image or vector rectangle.
        raster_source: Path | None = None
        raster_asset_id = page["display_asset_id"]
        if page["source_kind"] != "pdf":
            raster_asset_id = raster_asset_id or page["original_asset_id"]
        if raster_asset_id:
            asset = conn.execute(
                "SELECT relative_path FROM assets WHERE id = ?",
                (raster_asset_id,),
            ).fetchone()
            if asset is not None:
                try:
                    raster_path = resolve_within(project_dir, asset["relative_path"])
                except ValueError:
                    raster_path = None
                if raster_path is not None and raster_path.exists():
                    raster_source = raster_path

    base_width = int(page_width) if page_width else None
    base_height = int(page_height) if page_height else None

    if run is None:
        return _empty("no_ocr_run", None, base_width, base_height)
    if run["status"] in {"queued", "running", "cancelling"}:
        return _empty("ocr_not_ready", run, base_width, base_height)
    if run["status"] == "cancelled":
        return _empty("ocr_cancelled", run, base_width, base_height)
    if run["status"] != "succeeded":
        return _empty("ocr_failed", run, base_width, base_height)

    current_asset = page["display_asset_id"] or page["original_asset_id"]
    if run["source_asset_id"] != current_asset or int(run["rotation"]) != int(
        page["rotation"]
    ):
        return _empty("ocr_stale", run, base_width, base_height)
    if not page_width or not page_height:
        return _empty("no_geometry", run, base_width, base_height)
    if not blocks:
        return _empty("no_geometry", run, base_width, base_height)

    proposals: list[dict[str, Any]] = []
    for kind, reason, gap_ratio in (
        ("table", "table_text_grid", 0.5),
        ("equation", "equation_text", 0.35),
    ):
        members = [block for block in blocks if block["kind"] == kind]
        for rect in _cluster(members, gap_ratio):
            clamped = clamp_rect(rect, int(page_width), int(page_height))
            if clamped is None:
                continue
            proposals.append(
                _proposal(
                    clamped,
                    kind=kind,
                    reason=reason,
                    confidence="high",
                    block_ids=[
                        block["id"] for block in members if _intersection(rect, block) > 0
                    ],
                )
            )

    image_rects: list[Rect] = []
    drawing_rects: list[Rect] = []
    raster_rects: list[Rect] = []
    if pdf_source is not None:
        pdf_path, pdf_index = pdf_source
        document = None
        try:
            document = pdf_service.open_document(pdf_path)
        except Exception:
            document = None
        if document is not None:
            try:
                image_rects = _image_rects(
                    pdf_service.image_regions(document, pdf_index, int(page_width)),
                    int(page_width),
                    int(page_height),
                )
                drawing_rects = _drawing_rects(
                    pdf_service.drawing_regions(document, pdf_index, int(page_width)),
                    int(page_width),
                    int(page_height),
                )
            finally:
                pdf_service.close_document(document)

    # A PDF page is rendered as well. When the document exposed no embedded image
    # or vector rectangle, that render is the only evidence left for an opaque
    # drawing (a scanned page, or artwork stored as form content). Raster ink is
    # weaker than PDF geometry, so it is offered with low confidence and never
    # saved on its own; when PDF evidence already exists it is skipped to avoid
    # proposing the same figure twice.
    if raster_source is not None and (
        pdf_source is None or not (image_rects or drawing_rects)
    ):
        raster_rects = artwork_service.artwork_regions(
            raster_source, blocks, int(page_width), int(page_height)
        )

    text_regions = [
        proposal
        for proposal in proposals
        if proposal["kind"] in {"table", "equation"}
    ]
    figures = assemble_figures(
        int(page_width),
        int(page_height),
        blocks,
        image_rects,
        drawing_rects,
        raster_rects,
        text_regions,
    )

    for figure in figures:
        clamped = clamp_rect(figure["rect"], int(page_width), int(page_height))
        if clamped is None:
            continue
        proposals.append(
            _proposal(
                clamped,
                kind="figure",
                reason=figure["reason"],
                confidence=figure["confidence"],
                caption=figure["caption"],
                block_ids=figure["block_ids"],
            )
        )

    proposals.sort(key=lambda item: (item["y"], item["x"], item["kind"]))
    filtered: list[dict[str, Any]] = []
    for proposal in proposals:
        if any(already_extracted(proposal, element) for element in existing):
            continue
        if any(iou(proposal, kept) >= DEDUPE_IOU for kept in filtered):
            continue
        filtered.append(proposal)
        if len(filtered) >= MAX_PROPOSALS:
            break

    return {
        "status": "ready",
        "page_width": base_width,
        "page_height": base_height,
        "ocr_run_id": run["id"],
        "engine": run["engine"],
        "proposals": filtered,
    }


DEFAULT_PROJECT_REVIEW_PAGES = 100
MAX_PROJECT_REVIEW_PAGES = 200


def propose_project_regions(
    project_dir: Path,
    *,
    limit: int = DEFAULT_PROJECT_REVIEW_PAGES,
    after_page_number: int | None = None,
) -> dict[str, Any]:
    """Aggregate read-only region proposals across a project's pages.

    Each page is evaluated with :func:`propose_regions`, so the identity and
    staleness rules are exactly the same as the per-page endpoint: a proposal is
    only returned for a successful OCR run whose ``source_asset_id`` and
    ``rotation`` still match the page. Nothing is persisted and no crop is
    created; the caller navigates to a page and reviews it through the normal
    element flow.

    Pages are processed in page order and the scan is bounded by ``limit`` so an
    explicit cross-page review cannot walk an unbounded document in one request.
    Pages without proposals are omitted, but the returned ``next_page_number``
    lets a caller continue after the processed window.
    """
    bounded = max(1, min(int(limit), MAX_PROJECT_REVIEW_PAGES))
    query = "SELECT id, page_number FROM pages"
    params: list[Any] = []
    if after_page_number is not None:
        query += " WHERE page_number > ?"
        params.append(int(after_page_number))
    query += " ORDER BY page_number ASC LIMIT ?"
    params.append(bounded + 1)
    with project_db(project_dir) as conn:
        rows = conn.execute(query, params).fetchall()

    truncated = len(rows) > bounded
    next_page_number = (
        int(rows[bounded]["page_number"]) if truncated else None
    )
    rows = rows[:bounded]

    pages: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        result = propose_regions(project_dir, row["id"])
        proposals = result["proposals"]
        if not proposals:
            continue
        total += len(proposals)
        pages.append(
            {
                "page_id": row["id"],
                "page_number": int(row["page_number"]),
                "status": result["status"],
                "page_width": result["page_width"],
                "page_height": result["page_height"],
                "ocr_run_id": result["ocr_run_id"],
                "engine": result["engine"],
                "proposal_count": len(proposals),
                "proposals": proposals,
            }
        )

    return {
        "pages": pages,
        "total_proposals": total,
        "pages_with_proposals": len(pages),
        "truncated": truncated,
        "next_page_number": next_page_number,
    }


EQUATION_GAP_RATIO = 0.35


def propose_page_equations(project_dir: Path, page_id: str) -> dict[str, Any]:
    """List equation regions on a page for user review.

    Only blocks the layout classifier labelled ``equation`` are proposed; inline
    math inside a paragraph is not a block of its own and is never invented. Nearby
    equation blocks are clustered the same way region proposals cluster them, then
    ordered top-to-bottom and left-to-right. The OCR text is a starting point only:
    nothing is saved, transcribed or inserted, and the caller must review the LaTeX
    preview through the normal equation dialog.
    """
    ocr_service.recover_active_runs(project_dir, page_id)
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        page_width = page["width"]
        page_height = page["height"]
        run = conn.execute(
            "SELECT * FROM ocr_runs WHERE page_id = ? ORDER BY created_at DESC LIMIT 1",
            (page_id,),
        ).fetchone()
        blocks: list[dict[str, Any]] = []
        words_by_block: dict[str, list[dict[str, Any]]] = {}
        if run is not None:
            rows = conn.execute(
                "SELECT * FROM ocr_blocks WHERE run_id = ? ORDER BY block_index ASC",
                (run["id"],),
            ).fetchall()
            blocks = [block for row in rows if (block := _block_dict(row)) is not None]
            words_by_block = {row["id"]: _row_words(row) for row in rows}
        existing = [
            {
                "x": float(row["x"]),
                "y": float(row["y"]),
                "width": float(row["width"]),
                "height": float(row["height"]),
            }
            for row in conn.execute(
                "SELECT x, y, width, height FROM elements WHERE page_id = ?",
                (page_id,),
            ).fetchall()
        ]

    base_width = int(page_width) if page_width else None
    base_height = int(page_height) if page_height else None

    def payload(status: str, proposals: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "status": status,
            "page_id": page_id,
            "page_width": base_width,
            "page_height": base_height,
            "ocr_run_id": run["id"] if run is not None else None,
            "engine": run["engine"] if run is not None else None,
            "proposals": proposals,
        }

    if run is None:
        return payload("no_ocr_run", [])
    if run["status"] in {"queued", "running", "cancelling"}:
        return payload("ocr_not_ready", [])
    if run["status"] == "cancelled":
        return payload("ocr_cancelled", [])
    if run["status"] != "succeeded":
        return payload("ocr_failed", [])
    current_asset = page["display_asset_id"] or page["original_asset_id"]
    if run["source_asset_id"] != current_asset or int(run["rotation"]) != int(
        page["rotation"]
    ):
        return payload("ocr_stale", [])
    if not base_width or not base_height:
        return payload("no_geometry", [])
    if not blocks:
        return payload("no_geometry", [])

    members = [block for block in blocks if block["kind"] == "equation"]
    proposals: list[dict[str, Any]] = []
    for rect in _cluster(members, EQUATION_GAP_RATIO):
        clamped = clamp_rect(rect, base_width, base_height)
        if clamped is None:
            continue
        contributing = sorted(
            (block for block in members if _intersection(rect, block) > 0),
            key=lambda block: (block["y"], block["x"]),
        )
        text = " ".join(
            block["text"].strip() for block in contributing if block["text"].strip()
        )
        # The LaTeX starting point is rebuilt from the stored word boxes when
        # they exist, so superscripts and subscripts survive. It falls back to
        # normalising the OCR text, and never guesses a character Tesseract did
        # not read: the preview still decides what may be inserted.
        latex_parts = [
            equation_latex.equation_latex_from_words(
                words_by_block.get(block["id"], []), block["text"].strip()
            )
            for block in contributing
        ]
        latex = " ".join(part for part in latex_parts if part).strip()
        proposals.append(
            {
                "key": (
                    f"equation-{clamped['x']}-{clamped['y']}-"
                    f"{clamped['width']}-{clamped['height']}"
                ),
                "x": clamped["x"],
                "y": clamped["y"],
                "width": clamped["width"],
                "height": clamped["height"],
                "text": text,
                "latex": latex,
                # An OCR equation block is a standalone block, so the proposal is
                # display math. Inline math inside a paragraph never becomes a
                # block of its own, so it is not guessed at here.
                "display": True,
                "confidence": "high",
                "reason": "equation_text",
                "block_ids": [block["id"] for block in contributing],
                "reading_index": 0,
            }
        )

    proposals.sort(key=lambda item: (item["y"], item["x"]))
    filtered: list[dict[str, Any]] = []
    for proposal in proposals:
        if any(already_extracted(proposal, element) for element in existing):
            continue
        if any(iou(proposal, kept) >= DEDUPE_IOU for kept in filtered):
            continue
        proposal["reading_index"] = len(filtered)
        filtered.append(proposal)
        if len(filtered) >= MAX_PROPOSALS:
            break

    return payload("ready", filtered)
