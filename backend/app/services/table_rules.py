"""Find straight table rules drawn in a raster image.

A scanned or photographed table often keeps its cell borders, but the word-box
grid cannot see them: a merged cell looks like two empty columns and a wrapped
header looks like an extra row. This module finds long, straight horizontal and
vertical strokes and returns their pixel coordinates, so the same deterministic
grid builder used for PDF rules can reconstruct the table.

The rules are intentionally conservative:

* detection runs on a bounded grayscale copy, so a large photo cannot make the
  request slow;
* a stroke must be much longer than text, which keeps letters and underlines out;
* adjacent scan rows or columns of one thick stroke are merged into one boundary;
* a table on a full page is measured inside its own region, so its shorter cell
  borders are not discarded for being small next to the page;
* the result is geometry only. Whether the strokes form a closed, usable table is
  decided by the caller's existing grid validation, which also rejects charts,
  open frames and mostly empty grids.

Nothing is written to the image, and no text is invented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# A scan larger than this is measured on a scaled copy. Coordinates are mapped
# back to the original pixels before they are returned.
MAX_SCAN_SIDE = 900
# A rule must span at least this share of the measured region. Text runs are far
# shorter; an underline or a short decoration is ignored.
MIN_RUN_RATIO = 0.2
# Even a very small region needs a stroke longer than a glyph before it counts.
MIN_RUN_PIXELS = 12
# JPEG and scan noise can break a stroke by a pixel or two.
MAX_GAP_PIXELS = 4
# A threshold outside this range means the image is not a normal ink-on-paper
# scan. The bounded values keep a dark photo or a blank page from producing
# meaningless strokes.
MIN_THRESHOLD = 40
MAX_THRESHOLD = 210
# A malformed or extremely busy region is refused instead of returning thousands
# of strokes that no grid builder could use safely.
MAX_SEGMENTS = 4_000

Rule = tuple[float, float, float]
Region = tuple[float, float, float, float]


@dataclass(frozen=True)
class Scan:
    """A bounded grayscale copy of an image, reusable for several regions.

    A page is decoded and downscaled once, then each candidate table is measured
    in its own region. That keeps a short cell border measurable without
    scanning the same page image again for every block.
    """

    gray: Image.Image
    inverse_scale: float
    width: int
    height: int


def _otsu_threshold(histogram: list[int]) -> int:
    """Return a dark/light split that separates ink from the paper."""
    total = sum(histogram)
    if total == 0:
        return 160
    sum_all = sum(index * count for index, count in enumerate(histogram))
    weight_background = 0
    sum_background = 0.0
    best_variance = -1.0
    threshold = 160

    for index, count in enumerate(histogram):
        weight_background += count
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += index * count
        mean_background = sum_background / weight_background
        mean_foreground = (sum_all - sum_background) / weight_foreground
        variance = (
            weight_background
            * weight_foreground
            * (mean_background - mean_foreground) ** 2
        )
        if variance > best_variance:
            best_variance = variance
            threshold = index

    return max(MIN_THRESHOLD, min(MAX_THRESHOLD, threshold))


def _runs(
    values: list[int], threshold: int, minimum: int, gap: int
) -> list[tuple[int, int]]:
    """Return dark runs, bridging small light gaps caused by scanning."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    last_dark = -1
    for index, value in enumerate(values):
        if value < threshold:
            if start is None:
                start = index
            last_dark = index
        elif start is not None and index - last_dark > gap:
            if last_dark - start + 1 >= minimum:
                runs.append((start, last_dark))
            start = None
            last_dark = -1
    if start is not None and last_dark - start + 1 >= minimum:
        runs.append((start, last_dark))
    return runs


def _merge_strokes(
    rows: list[tuple[float, list[tuple[float, float]]]], tolerance: float
) -> list[Rule]:
    """Collapse the scan rows or columns that belong to one thick stroke.

    One representative row is kept per group. Joining every row's spans would
    fill real gaps in a boundary, so the row that carries the most ink is used.
    """
    groups: list[tuple[list[float], list[list[tuple[float, float]]]]] = []
    for position, spans in sorted(rows):
        if groups and position - groups[-1][0][-1] <= tolerance:
            groups[-1][0].append(position)
            groups[-1][1].append(spans)
        else:
            groups.append(([position], [spans]))

    merged: list[Rule] = []
    for positions, span_lists in groups:
        best = max(
            span_lists,
            key=lambda spans: sum(end - start for start, end in spans),
        )
        centre = sum(positions) / len(positions)
        merged.extend((centre, start, end) for start, end in best)
    return merged


def _region_box(scan: Scan, region: Region | None) -> tuple[int, int, int, int] | None:
    """Map an original-pixel region onto the scan, or ``None`` when unusable."""
    gray_width, gray_height = scan.gray.size
    if region is None:
        return (0, 0, gray_width, gray_height)
    left, top, right, bottom = region
    if not all(math.isfinite(value) for value in region):
        return None
    if right - left < MIN_RUN_PIXELS or bottom - top < MIN_RUN_PIXELS:
        return None
    scale = 1.0 / scan.inverse_scale
    box = (
        max(0, int(math.floor(left * scale))),
        max(0, int(math.floor(top * scale))),
        min(gray_width, int(math.ceil(right * scale))),
        min(gray_height, int(math.ceil(bottom * scale))),
    )
    if box[2] - box[0] < MIN_RUN_PIXELS or box[3] - box[1] < MIN_RUN_PIXELS:
        return None
    return box


def load_scan(image_path: Path) -> Scan | None:
    """Decode and downscale an image once, or return ``None`` if unreadable."""
    try:
        with Image.open(image_path) as image:
            gray = image.convert("L")
            width, height = gray.size
            if width < MIN_RUN_PIXELS or height < MIN_RUN_PIXELS:
                return None
            scale = min(1.0, MAX_SCAN_SIDE / max(width, height))
            if scale < 1.0:
                gray = gray.resize(
                    (max(1, round(width * scale)), max(1, round(height * scale))),
                    Image.BOX,
                )
            gray.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    return Scan(
        gray=gray,
        inverse_scale=width / gray.width,
        width=width,
        height=height,
    )


def scan_rules(
    scan: Scan, region: Region | None = None
) -> tuple[list[Rule], list[Rule]]:
    """Return horizontal and vertical rule segments inside ``region``.

    A segment is ``(position, start, end)`` in original image pixels. ``region``
    is ``(left, top, right, bottom)`` in the same pixels and is clamped to the
    image. A region that is too small or carries no plausible strokes returns two
    empty lists, so the caller can keep its word-box grid.
    """
    box = _region_box(scan, region)
    if box is None:
        return [], []
    left, top, right, bottom = box
    crop = scan.gray.crop(box)
    scan_width, scan_height = crop.size
    if scan_width < MIN_RUN_PIXELS or scan_height < MIN_RUN_PIXELS:
        return [], []

    threshold = _otsu_threshold(crop.histogram())
    pixels = list(crop.getdata())

    minimum_x = max(MIN_RUN_PIXELS, round(scan_width * MIN_RUN_RATIO))
    minimum_y = max(MIN_RUN_PIXELS, round(scan_height * MIN_RUN_RATIO))
    inverse_scale = scan.inverse_scale
    offset_x = left * inverse_scale
    offset_y = top * inverse_scale
    tolerance = max(3.0, 2.0 * inverse_scale)

    horizontal_rows: list[tuple[float, list[tuple[float, float]]]] = []
    for y in range(scan_height):
        offset = y * scan_width
        row = pixels[offset : offset + scan_width]
        runs = _runs(row, threshold, minimum_x, MAX_GAP_PIXELS)
        if not runs:
            continue
        horizontal_rows.append(
            (
                offset_y + y * inverse_scale,
                [
                    (
                        offset_x + start * inverse_scale,
                        offset_x + (end + 1) * inverse_scale,
                    )
                    for start, end in runs
                ],
            )
        )
        if len(horizontal_rows) > MAX_SEGMENTS:
            return [], []

    vertical_rows: list[tuple[float, list[tuple[float, float]]]] = []
    for x in range(scan_width):
        column = pixels[x::scan_width]
        runs = _runs(column, threshold, minimum_y, MAX_GAP_PIXELS)
        if not runs:
            continue
        vertical_rows.append(
            (
                offset_x + x * inverse_scale,
                [
                    (
                        offset_y + start * inverse_scale,
                        offset_y + (end + 1) * inverse_scale,
                    )
                    for start, end in runs
                ],
            )
        )
        if len(vertical_rows) > MAX_SEGMENTS:
            return [], []

    return (
        _merge_strokes(horizontal_rows, tolerance),
        _merge_strokes(vertical_rows, tolerance),
    )


def detect_table_rules(
    image_path: Path, region: Region | None = None
) -> tuple[list[Rule], list[Rule]]:
    """Measure one image once and return its rule segments.

    Use :func:`load_scan` and :func:`scan_rules` instead when several regions of
    the same page are measured, so the image is decoded only once.
    """
    scan = load_scan(image_path)
    if scan is None:
        return [], []
    return scan_rules(scan, region)
