from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.errors import AppError
from app.services.layout import classify_text_block

try:  # PyMuPDF is a free, local dependency but stays optional at runtime.
    import pymupdf
except ImportError:  # pragma: no cover - exercised only on incomplete installs
    pymupdf = None  # type: ignore[assignment]


def pdf_available() -> bool:
    return pymupdf is not None


def _require_support():
    if pymupdf is None:
        raise AppError(
            409,
            "pdf_unavailable",
            "PDF support is not installed on this device.",
        )
    return pymupdf


def open_document(path: Path):
    """Open and validate a PDF, converting library errors to typed app errors."""
    module = _require_support()
    try:
        document = module.open(path)
    except Exception as exc:
        raise AppError(422, "pdf_unreadable", "The PDF file could not be read.") from exc
    if document.needs_pass:
        document.close()
        raise AppError(
            422,
            "pdf_encrypted",
            "Password-protected PDFs are not supported. Remove the password first.",
        )
    if document.page_count == 0:
        document.close()
        raise AppError(422, "pdf_empty", "The PDF does not contain any pages.")
    return document


def validate_document(path: Path, max_pages: int) -> int:
    document = open_document(path)
    try:
        if document.page_count > max_pages:
            raise AppError(
                422,
                "pdf_too_many_pages",
                f"The PDF has {document.page_count} pages; the limit is {max_pages}.",
            )
        return int(document.page_count)
    finally:
        document.close()


def render_page(document, index: int, dpi: int) -> Image.Image:
    module = _require_support()
    try:
        page = document.load_page(index)
        matrix = module.Matrix(dpi / 72.0, dpi / 72.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    except Exception as exc:
        raise AppError(
            422,
            "pdf_page_render_failed",
            f"PDF page {index + 1} could not be rendered.",
        ) from exc


def image_regions(document, index: int, target_width: int) -> list[dict[str, float]]:
    """Return the boxes of raster images drawn on a PDF page.

    ``Page.get_image_info`` reports where each embedded image is placed, not
    what it contains. Coordinates are converted to rendered-page pixels with
    the same width as the stored page, so a caller can compare them with the
    image the user sees. The page's own ``/Rotate`` value is applied; an
    unreadable page yields no regions instead of failing a whole request.

    Only geometry is returned. A box is a candidate, never proof that the
    region is a figure; the caller decides which boxes are worth proposing.
    """
    try:
        page = document.load_page(index)
        if page.rect.width <= 0:
            return []
        scale = target_width / float(page.rect.width)
        info = page.get_image_info()
        regions: list[dict[str, float]] = []
        for item in info:
            bbox = item.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            rect = pymupdf.Rect(*[float(value) for value in bbox[:4]])
            rect = rect * page.rotation_matrix
            width = rect.width * scale
            height = rect.height * scale
            if width < 1 or height < 1:
                continue
            regions.append(
                {
                    "x": rect.x0 * scale,
                    "y": rect.y0 * scale,
                    "width": width,
                    "height": height,
                }
            )
        return regions
    except Exception:
        return []


def table_lines(
    document, index: int, target_width: int
) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[float, float, float]],
]:
    """Return horizontal and vertical rule segments drawn on a PDF page.

    Each horizontal rule is ``(y, x0, x1)`` and each vertical rule is
    ``(x, y0, y1)`` in rendered-page pixels. Only axis-aligned strokes and thin
    filled rectangles are returned. Curves, diagonal lines and filled areas are
    ignored because they cannot describe a rectangular cell. A page that cannot
    be read yields no rules instead of failing the request.
    """
    try:
        page = document.load_page(index)
        if page.rect.width <= 0:
            return [], []
        scale = target_width / float(page.rect.width)
        drawings = page.get_drawings()
    except Exception:
        return [], []

    matrix = page.rotation_matrix
    horizontals: list[tuple[float, float, float]] = []
    verticals: list[tuple[float, float, float]] = []

    def add_segment(ax: float, ay: float, bx: float, by: float) -> None:
        if abs(ay - by) <= 1.0 and abs(bx - ax) >= 2.0:
            horizontals.append(
                (
                    round(((ay + by) / 2) * scale, 2),
                    round(min(ax, bx) * scale, 2),
                    round(max(ax, bx) * scale, 2),
                )
            )
        elif abs(ax - bx) <= 1.0 and abs(by - ay) >= 2.0:
            verticals.append(
                (
                    round(((ax + bx) / 2) * scale, 2),
                    round(min(ay, by) * scale, 2),
                    round(max(ay, by) * scale, 2),
                )
            )

    for path in drawings:
        # A filled cell background may also be stroked; its outline is still a
        # real rule, so the stroke presence decides and the fill does not matter.
        stroked = path.get("color") is not None
        for item in path.get("items", ()):
            if not item:
                continue
            kind = item[0]
            if kind == "l" and len(item) >= 3:
                start = item[1] * matrix
                end = item[2] * matrix
                add_segment(start.x, start.y, end.x, end.y)
            elif kind == "re" and len(item) >= 2:
                rect = _module_rect(item[1], matrix)
                width = rect.width
                height = rect.height
                if height <= 2.0 and width >= 8.0:
                    middle = (rect.y0 + rect.y1) / 2
                    add_segment(rect.x0, middle, rect.x1, middle)
                elif width <= 2.0 and height >= 8.0:
                    middle = (rect.x0 + rect.x1) / 2
                    add_segment(middle, rect.y0, middle, rect.y1)
                elif stroked:
                    # A stroked rectangle's four edges are real rules, even
                    # though the whole rectangle is not a thin fill.
                    add_segment(rect.x0, rect.y0, rect.x1, rect.y0)
                    add_segment(rect.x0, rect.y1, rect.x1, rect.y1)
                    add_segment(rect.x0, rect.y0, rect.x0, rect.y1)
                    add_segment(rect.x1, rect.y0, rect.x1, rect.y1)
    return horizontals, verticals


def _module_rect(rect, matrix):
    """Return a page rectangle transformed and normalised by a page matrix."""
    return pymupdf.Rect(rect) * matrix


# A vector drawing is made of one or more paths. An axis-aligned thin or
# unfilled path is a rule, not artwork, so table grids, underlines and page
# frames are left to ``table_lines``. Parts closer than the join gap belong to
# the same drawing.
DRAWING_MIN_SIDE = 1.0
DRAWING_RULE_THICKNESS = 2.0
DRAWING_JOIN_GAP = 12.0
# A page with more artwork paths than this is either a whole-page vector
# illustration or a pathological export. Bounding the work keeps the suggestion
# request predictable; such a page can still be cropped by hand.
MAX_DRAWING_PATHS = 1500


def _artwork_path(path, width: float, height: float) -> bool:
    """Return whether one drawing path carries artwork rather than a rule."""
    if path.get("fill") is not None and min(width, height) > DRAWING_RULE_THICKNESS:
        return True
    for item in path.get("items", ()):
        if not item:
            continue
        kind = item[0]
        if kind in {"c", "qu"}:
            return True
        if kind == "l" and len(item) >= 3:
            start, end = item[1], item[2]
            if abs(start.x - end.x) > 1.0 and abs(start.y - end.y) > 1.0:
                return True
    return False


def drawing_regions(document, index: int, target_width: int) -> list[dict[str, float]]:
    """Return boxes of vector artwork drawn on a PDF page.

    A figure that exists only as vector paths has no raster image and no caption
    to anchor on. Curves, diagonals and filled shapes are the local evidence
    that a path is artwork; axis-aligned thin or unfilled paths are rules and are
    ignored, so a drawn table grid or a page frame never becomes a figure box.
    Nearby parts are grouped, and a group is only kept when it has several parts
    or a curved or diagonal one, because a single filled rectangle is far more
    often shading than an illustration.

    Coordinates are rendered-page pixels at the stored page width. Only geometry
    is returned: the caller decides which boxes are worth proposing. A page that
    cannot be read yields no regions instead of failing the request.
    """
    try:
        page = document.load_page(index)
        if page.rect.width <= 0:
            return []
        scale = target_width / float(page.rect.width)
        matrix = page.rotation_matrix
        drawings = page.get_drawings()
    except Exception:
        return []

    pieces: list[tuple[float, float, float, float, bool]] = []
    for path in drawings:
        rect = path.get("rect")
        if rect is None:
            continue
        rect = _module_rect(rect, matrix)
        width = rect.width * scale
        height = rect.height * scale
        if width < DRAWING_MIN_SIDE or height < DRAWING_MIN_SIDE:
            continue
        if not _artwork_path(path, width, height):
            continue
        complex_path = any(
            item and item[0] in {"c", "qu"} for item in path.get("items", ())
        )
        pieces.append(
            (rect.x0 * scale, rect.y0 * scale, rect.x1 * scale, rect.y1 * scale, complex_path)
        )
        if len(pieces) > MAX_DRAWING_PATHS:
            return []

    return _cluster_pieces(pieces)


def _cluster_pieces(
    pieces: list[tuple[float, float, float, float, bool]],
) -> list[dict[str, float]]:
    """Group artwork paths that touch, then keep groups that look like a drawing."""
    parents = list(range(len(pieces)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    def gap(start: float, end: float, other_start: float, other_end: float) -> float:
        return max(0.0, max(start, other_start) - min(end, other_end))

    # Sorting by the left edge lets the sweep stop as soon as a later piece is
    # too far away, instead of comparing every pair on a drawing-heavy page.
    order = sorted(range(len(pieces)), key=lambda index: pieces[index][0])
    for position, first in enumerate(order):
        left, top, right, bottom, _complex = pieces[first]
        for second in order[position + 1 :]:
            other_left, other_top, other_right, other_bottom, _other = pieces[second]
            if other_left - right > DRAWING_JOIN_GAP:
                break
            if gap(top, bottom, other_top, other_bottom) > DRAWING_JOIN_GAP:
                continue
            union(first, second)

    groups: dict[int, list[int]] = {}
    for index in range(len(pieces)):
        groups.setdefault(find(index), []).append(index)

    regions: list[dict[str, float]] = []
    for members in groups.values():
        if len(members) < 2 and not pieces[members[0]][4]:
            continue
        left = min(pieces[index][0] for index in members)
        top = min(pieces[index][1] for index in members)
        right = max(pieces[index][2] for index in members)
        bottom = max(pieces[index][3] for index in members)
        regions.append(
            {
                "x": round(left, 2),
                "y": round(top, 2),
                "width": round(right - left, 2),
                "height": round(bottom - top, 2),
            }
        )
    return regions


def extract_text(
    document, index: int, scale: float
) -> tuple[str, list[dict[str, Any]]]:
    """Extract the embedded text layer in reading order.

    Coordinates are converted from PDF points to rendered-page pixels so blocks
    line up with the image shown in the workspace. Embedded text has no OCR
    confidence score, so ``confidence`` stays ``None`` rather than pretending to
    be certain.
    """
    try:
        page = document.load_page(index)
        data = page.get_text("dict", sort=True)
        try:
            raw_words = page.get_text("words")
        except Exception:
            raw_words = []
        page_height = float(page.rect.height) * scale
    except Exception:
        return "", []

    prepared: list[dict[str, Any]] = []
    line_heights: list[float] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        line_spans: list[list[tuple[float, float]]] = []
        block_line_heights: list[float] = []
        max_height = 0.0
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text")]
            text = "".join(str(span["text"]) for span in spans).strip()
            if not text:
                continue
            lines.append(text)
            line_spans.append(
                sorted(
                    (float(span["bbox"][0]), float(span["bbox"][2]))
                    for span in spans
                    if len(span.get("bbox", ())) >= 4
                )
            )
            size = max((float(span.get("size", 0) or 0) for span in spans), default=0.0)
            max_height = max(max_height, size)
            # Measure the line itself, not the whole block. A multi-line body
            # block would otherwise inflate the page median and hide a real
            # heading above it.
            span_boxes = [
                tuple(float(value) for value in span["bbox"])
                for span in spans
                if len(span.get("bbox", ())) >= 4
            ]
            line_height = max(
                (box[3] - box[1] for box in span_boxes), default=0.0
            )
            line_height = max(line_height, size * 1.2, 1.0)
            block_line_heights.append(line_height)
            line_heights.append(line_height)
        text = "\n".join(lines).strip()
        if not text:
            continue
        x0, y0, x1, y1 = (float(value) for value in block.get("bbox", (0, 0, 0, 0)))
        height = max(y1 - y0, max(block_line_heights, default=0.0), 1.0)
        width = max(x1 - x0, 1.0)
        prepared.append(
            {
                "text": text,
                "x": round(x0 * scale),
                "y": round(y0 * scale),
                "width": round(width * scale),
                "height": round(height * scale),
                "line_count": len(lines),
                "word_count": sum(len(line.split()) for line in lines),
                "max_line_height": max(
                    block_line_heights, default=max(max_height * 1.2, 1.0)
                ),
                "bbox": (x0, y0, x1, y1),
                "line_spans": line_spans,
                "words": [],
            }
        )

    if not prepared:
        return "", []

    # ``words`` carries exact word boxes, which a table proposal can use. Each
    # word is attached to the text block that contains its centre. Nothing is
    # estimated from character widths, so a proposal never invents geometry.
    for raw_word in raw_words:
        if len(raw_word) < 8:
            continue
        word_text = str(raw_word[4]).strip()
        if not word_text:
            continue
        wx0, wy0, wx1, wy1 = (float(value) for value in raw_word[:4])
        center_x = (wx0 + wx1) / 2
        center_y = (wy0 + wy1) / 2
        owner = None
        for item in prepared:
            bx0, by0, bx1, by1 = item["bbox"]
            if bx0 - 1 <= center_x <= bx1 + 1 and by0 - 1 <= center_y <= by1 + 1:
                owner = item
                break
        if owner is None:
            continue
        owner["words"].append(
            {
                "text": word_text,
                "confidence": None,
                "x": round(wx0 * scale),
                "y": round(wy0 * scale),
                "width": max(round((wx1 - wx0) * scale), 1),
                "height": max(round((wy1 - wy0) * scale), 1),
                "line": int(raw_word[6]),
            }
        )

    for item in prepared:
        item["words"].sort(key=lambda word: (word["line"], word["x"]))

    median_height = statistics.median(line_heights) if line_heights else 1.0
    blocks: list[dict[str, Any]] = []
    for block_number, item in enumerate(prepared, start=1):
        blocks.append(
            {
                "block_index": block_number,
                "kind": classify_text_block(
                    item["text"],
                    item["max_line_height"],
                    median_height,
                    item["word_count"],
                    y=item["y"],
                    height=item["height"],
                    page_height=page_height,
                    line_spans=item["line_spans"],
                ),
                "text": item["text"],
                "confidence": None,
                "x": item["x"],
                "y": item["y"],
                "width": item["width"],
                "height": item["height"],
                "line_count": item["line_count"],
                "word_count": item["word_count"],
                "words": item["words"],
            }
        )
    text = "\n\n".join(block["text"] for block in blocks)
    return text, blocks


def engine_version() -> str | None:
    if pymupdf is None:
        return None
    return getattr(pymupdf, "__version__", None) or getattr(pymupdf, "VersionBind", None)
