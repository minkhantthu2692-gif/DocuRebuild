"""Locate artwork on a raster page without any PDF geometry.

A photographed or scanned page has no vector layer, so an uncaptioned figure has
no rectangle to read. The remaining local evidence is ink: the OCR run already
locates the text, so dense ink that lies outside every text block and forms a
large connected cluster is a candidate figure. The pass returns boxes only and
never classifies what is inside them, so the result is a reviewable suggestion
rather than recognised content. Everything is deterministic and runs offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

# The page is analysed on a small grayscale copy: enough resolution to separate a
# figure from a text line, cheap enough to run on every suggestion request.
ANALYSIS_WIDTH = 480
GRID_COLUMNS = 64
# A cell counts as inked when at least this share of its pixels is dark.
INK_CELL_SHARE = 0.08
# A page whose own background is dark cannot be separated from its content.
MIN_BACKGROUND = 140
# A pixel is ink when it is clearly darker than the page's own background. The
# margin is wide enough to survive the averaging of a thin antialiased stroke,
# but narrow enough to ignore paper grain and soft shadows.
BACKGROUND_MARGIN = 30
MAX_THRESHOLD = 240
MIN_THRESHOLD = 120
# A figure suggestion must be worth reading. Small clusters are usually stray
# glyphs, rules, bullets or stamps.
MIN_WIDTH_RATIO = 0.15
MIN_HEIGHT_RATIO = 0.10
BACKGROUND_SHARE = 0.8
MIN_ASPECT = 1 / 12
MIN_INK_SHARE = 0.02
# Nearby parts of one drawing are joined, because a bar chart or a labelled
# diagram falls apart into many small clusters otherwise.
JOIN_GAP_RATIO = 0.03
MAX_REGIONS = 5
MAX_CLUSTERS = 400
PADDING_RATIO = 0.004

Bounds = tuple[int, int, int, int]
Box = tuple[float, float, float, float]


def _threshold(image: Image.Image) -> int | None:
    """Return the luma below which a pixel is ink, or ``None`` for a dark page."""
    histogram = image.histogram()
    total = sum(histogram)
    if total <= 0:
        return None
    running = 0
    background = 255
    for value in range(255, -1, -1):
        running += histogram[value]
        if running >= total * 0.1:
            background = value
            break
    if background < MIN_BACKGROUND:
        return None
    return min(MAX_THRESHOLD, max(MIN_THRESHOLD, background - BACKGROUND_MARGIN))


def _text_cells(
    blocks: list[dict[str, Any]],
    columns: int,
    rows: int,
    cell: int,
    width: int,
    height: int,
    page_width: int,
    page_height: int,
) -> set[int]:
    """Mark grid cells that overlap an OCR block.

    The OCR boxes bound the text tightly, so anything outside them is content the
    engine did not read as text. A cell that merely touches a block is masked
    too: a glyph usually bleeds a pixel or two past its box, and those leftover
    pixels would otherwise look like a small ink cluster next to the figure.
    """
    covered: set[int] = set()
    scale_x = width / page_width
    scale_y = height / page_height
    for block in blocks:
        left = max(0, int(block["x"] * scale_x))
        top = max(0, int(block["y"] * scale_y))
        right = min(width, int((block["x"] + block["width"]) * scale_x))
        bottom = min(height, int((block["y"] + block["height"]) * scale_y))
        if right <= left or bottom <= top:
            continue
        first_column = max(0, left // cell - 1)
        last_column = min(columns - 1, (right - 1) // cell + 1)
        first_row = max(0, top // cell - 1)
        last_row = min(rows - 1, (bottom - 1) // cell + 1)
        for row in range(first_row, last_row + 1):
            cell_top = row * cell
            cell_bottom = min(height, cell_top + cell)
            for column in range(first_column, last_column + 1):
                cell_left = column * cell
                cell_right = min(width, cell_left + cell)
                if (
                    cell_left < right
                    and cell_right > left
                    and cell_top < bottom
                    and cell_bottom > top
                ):
                    covered.add(row * columns + column)
    return covered


def _clusters(candidates: set[int], columns: int, rows: int) -> list[list[int]]:
    """Group touching candidate cells into eight-connected clusters."""
    remaining = set(candidates)
    clusters: list[list[int]] = []
    while remaining:
        start = remaining.pop()
        members = [start]
        stack = [start]
        while stack:
            index = stack.pop()
            row, column = divmod(index, columns)
            for row_step in (-1, 0, 1):
                next_row = row + row_step
                if next_row < 0 or next_row >= rows:
                    continue
                for column_step in (-1, 0, 1):
                    if row_step == 0 and column_step == 0:
                        continue
                    next_column = column + column_step
                    if next_column < 0 or next_column >= columns:
                        continue
                    neighbour = next_row * columns + next_column
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        members.append(neighbour)
                        stack.append(neighbour)
        clusters.append(members)
        if len(clusters) > MAX_CLUSTERS:
            return []
    return clusters


def _bounds(members: list[int], columns: int) -> Bounds:
    """Return the cell bounding box ``(left, top, right, bottom)`` of a cluster."""
    rows = [divmod(index, columns) for index in members]
    first_row = min(row for row, _column in rows)
    last_row = max(row for row, _column in rows)
    first_column = min(column for _row, column in rows)
    last_column = max(column for _row, column in rows)
    return first_column, first_row, last_column + 1, last_row + 1


def _group_bounds(group: list[int], areas: list[tuple[int, Bounds]]) -> Bounds:
    left = min(areas[index][1][0] for index in group)
    top = min(areas[index][1][1] for index in group)
    right = max(areas[index][1][2] for index in group)
    bottom = max(areas[index][1][3] for index in group)
    return left, top, right, bottom


def _near(first: Bounds, second: Bounds, gap: int) -> bool:
    horizontal = max(0, max(first[0], second[0]) - min(first[2], second[2]))
    vertical = max(0, max(first[1], second[1]) - min(first[3], second[3]))
    return max(horizontal, vertical) <= gap


def artwork_regions(
    path: Path,
    blocks: list[dict[str, Any]],
    page_width: int,
    page_height: int,
) -> list[dict[str, float]]:
    """Return boxes of ink that the OCR text layout does not explain.

    Only geometry is returned. A box is a candidate figure, never proof that the
    region is artwork, so the caller presents it for review with a low
    confidence. An unreadable image, a dark page or a page without a meaningful
    cluster yields no regions instead of failing the request.
    """
    if page_width <= 0 or page_height <= 0:
        return []
    try:
        with Image.open(path) as source:
            gray = source.convert("L")
            if gray.width <= 0 or gray.height <= 0:
                return []
            width = ANALYSIS_WIDTH
            height = max(1, round(gray.height * width / gray.width))
            small = gray.resize((width, height), Image.Resampling.BOX)
    except Exception:
        return []

    threshold = _threshold(small)
    if threshold is None:
        return []

    cell = max(4, width // GRID_COLUMNS)
    columns = (width + cell - 1) // cell
    rows = (height + cell - 1) // cell
    pixels = list(small.getdata())
    candidates: set[int] = set()
    for row in range(rows):
        top = row * cell
        bottom = min(height, top + cell)
        for column in range(columns):
            left = column * cell
            right = min(width, left + cell)
            area = (right - left) * (bottom - top)
            if area <= 0:
                continue
            dark = 0
            for y in range(top, bottom):
                start = y * width + left
                for value in pixels[start : start + (right - left)]:
                    if value < threshold:
                        dark += 1
            if dark / area >= INK_CELL_SHARE:
                candidates.add(row * columns + column)

    if not candidates:
        return []
    text = _text_cells(
        blocks, columns, rows, cell, width, height, page_width, page_height
    )
    candidates -= text
    if not candidates:
        return []

    clusters = _clusters(candidates, columns, rows)
    if not clusters:
        return []
    areas = [(len(members), _bounds(members, columns)) for members in clusters]

    # Join parts of one drawing, then keep only groups big enough to be a figure.
    # The gap is measured in grid cells, not pixels, because the cluster bounds
    # below are cell indices.
    join = max(1, round(max(columns, rows) * JOIN_GAP_RATIO))
    groups: list[list[int]] = [[index] for index in range(len(areas))]
    merged = True
    while merged:
        merged = False
        for first in range(len(groups)):
            if not groups[first]:
                continue
            for second in range(first + 1, len(groups)):
                if not groups[second]:
                    continue
                if _near(
                    _group_bounds(groups[first], areas),
                    _group_bounds(groups[second], areas),
                    join,
                ):
                    groups[first].extend(groups[second])
                    groups[second] = []
                    merged = True

    regions: list[dict[str, float]] = []
    minimum_width = page_width * MIN_WIDTH_RATIO
    minimum_height = page_height * MIN_HEIGHT_RATIO
    for group in groups:
        if not group:
            continue
        left, top, right, bottom = _group_bounds(group, areas)
        box_width = (right - left) * cell
        box_height = (bottom - top) * cell
        if box_width <= 0 or box_height <= 0:
            continue
        cells = sum(areas[index][0] for index in group)
        if cells / ((right - left) * (bottom - top)) < MIN_INK_SHARE:
            continue
        page_width_box = box_width * page_width / width
        page_height_box = box_height * page_height / height
        if page_width_box < minimum_width or page_height_box < minimum_height:
            continue
        if (
            page_width_box >= page_width * BACKGROUND_SHARE
            and page_height_box >= page_height * BACKGROUND_SHARE
        ):
            continue
        if page_height_box / page_width_box < MIN_ASPECT:
            continue
        if page_width_box / page_height_box < MIN_ASPECT:
            continue
        page_box: Box = (
            left * cell * page_width / width,
            top * cell * page_height / height,
            min(width, right * cell) * page_width / width,
            min(height, bottom * cell) * page_height / height,
        )
        edges = 0
        margin_x = page_width * 0.01
        margin_y = page_height * 0.01
        if page_box[0] <= margin_x:
            edges += 1
        if page_box[1] <= margin_y:
            edges += 1
        if page_box[2] >= page_width - margin_x:
            edges += 1
        if page_box[3] >= page_height - margin_y:
            edges += 1
        if edges >= 3:
            continue
        pad = max(2, round(page_width * PADDING_RATIO))
        pad = min(pad, round(page_width_box * 0.05))
        x = max(0.0, page_box[0] - pad)
        y = max(0.0, page_box[1] - pad)
        right_edge = min(float(page_width), page_box[2] + pad)
        bottom_edge = min(float(page_height), page_box[3] + pad)
        regions.append(
            {
                "x": round(x, 2),
                "y": round(y, 2),
                "width": round(right_edge - x, 2),
                "height": round(bottom_edge - y, 2),
            }
        )

    regions.sort(key=lambda rect: rect["width"] * rect["height"], reverse=True)
    return regions[:MAX_REGIONS]
