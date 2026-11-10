from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.errors import AppError
from app.db.project_schema import project_db

# A figure suggestion is anchored to a figure-like caption. Without a caption
# there is no reliable local signal that separates a drawing from empty space,
# so uncaptioned figures are left to manual selection.
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


def _iou(first: Rect, second: Rect) -> float:
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


def _clamp_rect(
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
        if any(_iou(rect, kept[0]) >= DEDUPE_IOU for kept in unique):
            continue
        unique.append((rect, caption))
    return unique


def _already_extracted(proposal: Rect, element: Rect) -> bool:
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
    return intersection / area >= 0.9 and _iou(proposal, element) >= 0.5


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


def propose_regions(project_dir: Path, page_id: str) -> dict[str, Any]:
    """Derive reviewable region proposals from the latest local OCR layout.

    Proposals are not persisted and never become elements on their own. The
    user reviews the rectangle and caption, then saves it through the normal
    crop path, so a bad suggestion costs nothing and is never treated as
    verified content.
    """
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

    base_width = int(page_width) if page_width else None
    base_height = int(page_height) if page_height else None

    if run is None:
        return _empty("no_ocr_run", None, base_width, base_height)
    if run["status"] in {"queued", "running"}:
        return _empty("ocr_not_ready", run, base_width, base_height)
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
            clamped = _clamp_rect(rect, int(page_width), int(page_height))
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

    for rect, caption in _figure_rects(blocks, int(page_width), int(page_height)):
        clamped = _clamp_rect(rect, int(page_width), int(page_height))
        if clamped is None:
            continue
        proposals.append(
            _proposal(
                clamped,
                kind="figure",
                reason="figure_caption_gap",
                confidence="medium",
                caption=caption["text"].strip()[:500],
                block_ids=[caption["id"]],
            )
        )

    proposals.sort(key=lambda item: (item["y"], item["x"], item["kind"]))
    filtered: list[dict[str, Any]] = []
    for proposal in proposals:
        if any(_already_extracted(proposal, element) for element in existing):
            continue
        if any(_iou(proposal, kept) >= DEDUPE_IOU for kept in filtered):
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
