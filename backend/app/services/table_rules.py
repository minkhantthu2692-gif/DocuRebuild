"""Find straight table rules drawn in a raster crop.

A scanned or photographed table often keeps its cell borders, but the word-box
grid cannot see them: a merged cell looks like two empty columns and a wrapped
header looks like an extra row. This module finds long, straight horizontal and
vertical strokes in the crop image and returns their pixel coordinates, so the
same deterministic grid builder used for PDF rules can reconstruct the table.

The rules are intentionally conservative:

* detection runs on a bounded copy of the crop, so a large photo cannot make the
  request slow;
* a stroke must be much longer than text, which keeps letters and underlines out;
* adjacent scan rows or columns of one thick stroke are merged into one boundary;
* the result is geometry only. Whether the strokes form a closed, usable table is
  decided by the caller's existing grid validation, which also rejects charts,
  open frames and mostly empty grids.

Nothing is written to the crop, and no text is invented.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# A crop larger than this is measured on a scaled copy. Coordinates are mapped
# back to the original pixels before they are returned.
MAX_SCAN_SIDE = 900
# A rule must span at least this share of the scanned width or height. Text runs
# are far shorter; an underline or a short decoration is ignored.
MIN_RUN_RATIO = 0.2
# Even a very small crop needs a stroke longer than a glyph before it counts.
MIN_RUN_PIXELS = 12
# JPEG and scan noise can break a stroke by a pixel or two.
MAX_GAP_PIXELS = 4
# A threshold outside this range means the crop is not a normal ink-on-paper
# image. The bounded values keep a dark photo or a blank page from producing
# meaningless strokes.
MIN_THRESHOLD = 40
MAX_THRESHOLD = 210
# A malformed or extremely busy crop is refused instead of returning thousands
# of strokes that no grid builder could use safely.
MAX_SEGMENTS = 4_000


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
) -> list[tuple[float, float, float]]:
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

    merged: list[tuple[float, float, float]] = []
    for positions, span_lists in groups:
        best = max(
            span_lists,
            key=lambda spans: sum(end - start for start, end in spans),
        )
        centre = sum(positions) / len(positions)
        merged.extend((centre, start, end) for start, end in best)
    return merged


def detect_table_rules(
    image_path: Path,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Return horizontal and vertical rule segments in crop pixels.

    A segment is ``(position, start, end)``. An image that cannot be read, or one
    that produces implausible strokes, returns two empty lists; the caller then
    keeps its word-box grid.
    """
    try:
        with Image.open(image_path) as image:
            gray = image.convert("L")
            width, height = gray.size
            if width < MIN_RUN_PIXELS or height < MIN_RUN_PIXELS:
                return [], []
            scale = min(1.0, MAX_SCAN_SIDE / max(width, height))
            if scale < 1.0:
                scan_size = (
                    max(1, round(width * scale)),
                    max(1, round(height * scale)),
                )
                gray = gray.resize(scan_size, Image.BOX)
            scan_width, scan_height = gray.size
            threshold = _otsu_threshold(gray.histogram())
            pixels = list(gray.getdata())
    except (OSError, ValueError, Image.DecompressionBombError):
        return [], []

    minimum_x = max(MIN_RUN_PIXELS, round(scan_width * MIN_RUN_RATIO))
    minimum_y = max(MIN_RUN_PIXELS, round(scan_height * MIN_RUN_RATIO))
    inverse_scale = width / scan_width
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
                y * inverse_scale,
                [
                    (start * inverse_scale, (end + 1) * inverse_scale)
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
                x * inverse_scale,
                [
                    (start * inverse_scale, (end + 1) * inverse_scale)
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
