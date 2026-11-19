"""Build a reviewable table proposal from stored OCR word boxes.

A table label from the layout heuristic only says "this text looks like a grid".
It does not give cells, so this module reads the engine's own word positions and
groups them into rows and columns. The result is a proposal: nothing is written
to the document, every empty cell stays empty, and a cell whose words are
uncertain is marked for review instead of being guessed.

The rules are deliberately conservative:

* Rows are clustered by vertical centre, so a word is never moved to another
  line to make a prettier grid.
* Columns are the vertical whitespace bands that no word crosses. A word that
  spans several bands is placed in the band it overlaps most, so text is never
  dropped.
* Only blocks the layout heuristic already labelled ``table`` are accepted.
  A paragraph is not silently turned into a table.
* A block the user corrected by hand is refused, because its stored word boxes
  describe the engine's original text rather than the corrected text.
* Caps keep a damaged scan from producing an unusable grid.
* Cell alignment is inferred only when the free space inside the column band
  makes left, centre and right clearly different. A cell whose lines disagree or
  nearly fill the band reports no alignment and keeps the default.
* A page-level detector groups consecutive blocks whose rows share aligned
  columns. This is how embedded PDF text becomes a table when the PDF layer
  stores one block per row. A group is accepted only when the deterministic
  layout classifier that labels single blocks also calls the merged rows a table.
* When a PDF page has drawn rules, the grid is read from those rules instead of
  from the whitespace between words. A separator that is not drawn across a
  cell is a merged cell: the span comes from the document's own geometry, not
  from a guess. The rule-based grid is only used for an unrotated, unedited PDF
  page whose immutable source still matches; otherwise the word-based grid is
  kept. A rule grid must look closed and mostly filled, so a chart's axis frame
  is not offered as a table.

The frontend shows the proposal for review and inserts it only when the user
approves it. The proposal also reports the pixel region it was read from, so the
review dialog can show the source crop beside the grid.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from math import ceil
from pathlib import Path
from statistics import median
from typing import Any

from app.core.errors import AppError
from app.core.storage import resolve_within
from app.db.project_schema import project_db
from app.services import image_edits as edits_service
from app.services import ocr as ocr_service
from app.services import pdf as pdf_service
from app.services.layout import classify_text_block

MAX_ROWS = 60
MAX_COLUMNS = 20
MAX_CELLS = 600
MAX_CANDIDATES = 20
MIN_ROWS = 2
MIN_COLUMNS = 2
LOW_CONFIDENCE = 60.0
ROW_TOLERANCE_RATIO = 0.6
COLUMN_GAP_RATIO = 0.6
MIN_BAND_WIDTH = 2.0
MIN_BAND_SUPPORT = 2
GROUP_GAP_RATIO = 2.0
MIN_GROUP_GAP = 24.0
# Vector rules are short strokes compared with text, so a segment shorter than
# this is a decoration (a bullet, an underline or a border corner), not a cell
# edge. Coordinates that differ by less than the tolerance are the same rule,
# either because a cell is drawn edge by edge or because a stroke was split.
MIN_RULE_LENGTH = 12.0
RULE_TOLERANCE = 3.0
# A chart's plot frame is also a drawn grid. Requiring real text and a
# conservative share of filled cells keeps an empty frame out of the proposals.
MIN_VECTOR_FILLED_CELLS = 2
MIN_VECTOR_FILL_RATIO = 0.2
# An OCR candidate inside a vector grid describes the same table with a coarser
# structure, so it is dropped rather than listed twice.
VECTOR_COVER_RATIO = 0.85

Word = dict[str, Any]
Band = tuple[float, float]
Grid = tuple[list[list[Word]], list[Band]]


def _page(conn, page_id: str):
    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if row is None:
        raise AppError(404, "page_not_found", "Page not found.")
    return row


def _parse_words(raw: str | None) -> list[Word]:
    """Read stored word boxes, ignoring anything malformed.

    The column is JSON because a block has a variable number of words. A bad
    entry is skipped rather than failing the whole proposal: the remaining words
    still describe a usable part of the table.
    """
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return _clean_words(data)


def _clean_words(data: list[Any]) -> list[Word]:
    """Normalise word entries, dropping any entry without usable geometry."""
    words: list[Word] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            x = float(item["x"])
            y = float(item["y"])
            width = float(item["width"])
            height = float(item["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue

        confidence = item.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = None
            else:
                if confidence < 0 or confidence > 100:
                    confidence = None

        try:
            line = int(item.get("line", 0))
        except (TypeError, ValueError):
            line = 0

        words.append(
            {
                "text": text.strip(),
                "confidence": confidence,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "line": line,
            }
        )
    return words


def _centre_y(word: Word) -> float:
    return word["y"] + word["height"] / 2


def _right(word: Word) -> float:
    return word["x"] + word["width"]


def _cluster_rows(words: list[Word]) -> list[list[Word]]:
    """Group words into visual rows without changing their reading order."""
    heights = [word["height"] for word in words if word["height"] > 0]
    typical_height = median(heights) if heights else 1.0
    tolerance = max(typical_height * ROW_TOLERANCE_RATIO, 1.0)

    rows: list[list[Word]] = []
    centres: list[float] = []
    for word in sorted(words, key=lambda item: (_centre_y(item), item["x"])):
        centre = _centre_y(word)
        match = None
        for index in range(len(rows) - 1, -1, -1):
            allowed = max(tolerance, word["height"] * ROW_TOLERANCE_RATIO)
            if abs(centre - centres[index]) <= allowed:
                match = index
                break
        if match is None:
            rows.append([word])
            centres.append(centre)
        else:
            rows[match].append(word)
            centres[match] = sum(_centre_y(item) for item in rows[match]) / len(
                rows[match]
            )

    ordered = sorted(zip(centres, rows), key=lambda pair: pair[0])
    return [row for _centre, row in ordered]


def _column_bands(rows: list[list[Word]], typical_height: float) -> list[Band]:
    """Find vertical whitespace bands that no word crosses."""
    left = min(word["x"] for row in rows for word in row)
    right = max(_right(word) for row in rows for word in row)
    # A single wide word (for example a title row above the grid) would bridge
    # every gutter. Leave such rows out of column detection; they still keep
    # their text in the grid below.
    spanning_width = max((right - left) * 0.6, 1.0)
    detection_rows = []
    for row in rows:
        row_width = max(_right(word) for word in row) - min(word["x"] for word in row)
        if len(row) >= 2 or row_width < spanning_width:
            detection_rows.append(row)
    if not detection_rows:
        detection_rows = rows

    intervals: list[Band] = []
    for row in detection_rows:
        for word in row:
            intervals.append((word["x"], max(_right(word), word["x"] + 1)))
    intervals.sort()

    gap = max(typical_height * COLUMN_GAP_RATIO, 3.0)
    merged: list[list[float]] = []
    for start, end in intervals:
        if merged and start - merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    bands = [(start, end) for start, end in merged if end - start >= MIN_BAND_WIDTH]
    if not bands:
        return []

    support = [0] * len(bands)
    for row in rows:
        hit: set[int] = set()
        for word in row:
            hit.add(_best_band(word, bands))
        for index in hit:
            support[index] += 1

    threshold = MIN_BAND_SUPPORT if len(rows) >= 3 else 1
    kept = [index for index, count in enumerate(support) if count >= threshold]
    if len(kept) < MIN_COLUMNS:
        return bands
    return [bands[index] for index in kept]


def _best_band(word: Word, bands: list[Band]) -> int:
    """Return the band a word belongs to, using the largest horizontal overlap."""
    start = word["x"]
    end = max(_right(word), start + 1)
    best = 0
    best_overlap = float("-inf")
    for index, (band_start, band_end) in enumerate(bands):
        overlap = min(end, band_end) - max(start, band_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best = index
    return best


def _cell_payload(
    words: list[Word],
    band: Band | None = None,
    typical_height: float = 1.0,
) -> dict[str, Any]:
    if not words:
        return {
            "text": "",
            "confidence": None,
            "uncertain": False,
            "empty": True,
            "alignment": None,
        }

    lines: dict[int, list[Word]] = {}
    for word in sorted(words, key=lambda item: (item["line"], item["x"])):
        lines.setdefault(word["line"], []).append(word)
    text = "\n".join(
        " ".join(word["text"] for word in line_words)
        for _line, line_words in sorted(lines.items())
    )

    confidences = [
        word["confidence"] for word in words if word["confidence"] is not None
    ]
    confidence = (
        round(sum(confidences) / len(confidences), 1) if confidences else None
    )
    # One weak word is enough to make the whole cell worth checking. A cell with
    # a mix of scored and unscored words is also uncertain: part of it is unknown.
    uncertain = bool(confidences) and (
        len(confidences) < len(words) or min(confidences) < LOW_CONFIDENCE
    )
    return {
        "text": text,
        "confidence": confidence,
        "uncertain": uncertain,
        "empty": False,
        "alignment": _cell_alignment(lines, band, typical_height),
    }


def _cell_alignment(
    lines: dict[int, list[Word]],
    band: Band | None,
    typical_height: float,
) -> str | None:
    """Infer the cell's text alignment from its position inside its column band.

    Alignment is only reported when the text leaves enough room in the band for
    the choice to be visible. A cell that fills the band looks identical whether
    it is left, centred or right aligned, so it reports nothing and keeps the
    default instead of claiming a value that cannot be observed. Lines inside one
    cell must agree; mixed alignment also reports nothing.
    """
    if band is None:
        return None
    band_start, band_end = band
    width = band_end - band_start
    if width <= 0:
        return None

    # A gap difference smaller than this cannot be told apart from rounding in
    # the OCR boxes, so the cell is treated as centred only when both margins are
    # comparable to this tolerance.
    tolerance = max(typical_height * 0.4, width * 0.08)
    votes: set[str] = set()
    for line_words in lines.values():
        left = min(word["x"] for word in line_words)
        right = max(_right(word) for word in line_words)
        free = width - (right - left)
        if free <= tolerance:
            # The line fills the band; no alignment can be observed.
            continue
        left_gap = left - band_start
        right_gap = band_end - right
        if abs(left_gap - right_gap) <= tolerance:
            votes.add("center")
        elif right_gap > left_gap:
            votes.add("left")
        else:
            votes.add("right")

    if len(votes) != 1:
        return None
    return votes.pop()


def _source_box(words: list[Word]) -> dict[str, float]:
    """Pixel region the proposal was read from, in the OCR image's coordinates.

    The frontend uses it to show the source crop next to the review grid. It is
    derived from the word boxes, so it always matches what was actually read.
    """
    left = min(word["x"] for word in words)
    top = min(word["y"] for word in words)
    right = max(_right(word) for word in words)
    bottom = max(word["y"] + word["height"] for word in words)
    return {
        "x": round(left, 1),
        "y": round(top, 1),
        "width": round(right - left, 1),
        "height": round(bottom - top, 1),
    }


def _grid_payload(rows: list[list[Word]], bands: list[Band]) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    uncertain_cells = 0
    empty_cells = 0
    has_confidence = False
    heights = [word["height"] for row in rows for word in row if word["height"] > 0]
    typical_height = median(heights) if heights else 1.0

    for row_index, row in enumerate(rows):
        buckets: list[list[Word]] = [[] for _ in bands]
        for word in row:
            buckets[_best_band(word, bands)].append(word)
        for column_index, bucket in enumerate(buckets):
            cell = _cell_payload(bucket, bands[column_index], typical_height)
            cells.append(
                {
                    "row": row_index,
                    "column": column_index,
                    **cell,
                }
            )
            if cell["uncertain"]:
                uncertain_cells += 1
            if cell["empty"]:
                empty_cells += 1
            if cell["confidence"] is not None:
                has_confidence = True

    warnings: list[str] = []
    if not has_confidence:
        warnings.append("no_confidence")
    if uncertain_cells:
        warnings.append("low_confidence")
    if empty_cells:
        warnings.append("empty_cells")

    return {
        "rows": len(rows),
        "columns": len(bands),
        "has_confidence": has_confidence,
        "uncertain_cells": uncertain_cells,
        "empty_cells": empty_cells,
        "warnings": warnings,
        "source": _source_box([word for row in rows for word in row]),
        "cells": cells,
    }


def _proposal(
    page,
    page_id: str,
    block_id: str,
    run_id: str,
    engine: str,
    rows: list[list[Word]],
    bands: list[Band],
) -> dict[str, Any]:
    return {
        "page_id": page_id,
        "block_id": block_id,
        "run_id": run_id,
        "engine": engine,
        "page_width": page["width"],
        "page_height": page["height"],
        **_grid_payload(rows, bands),
    }


def _build_grid(words: list[Word]) -> Grid | None:
    """Return a grid that respects every cap, or ``None`` for an unusable shape."""
    if not words:
        return None
    heights = [word["height"] for word in words if word["height"] > 0]
    typical_height = median(heights) if heights else 1.0
    rows = _cluster_rows(words)
    if len(rows) < MIN_ROWS:
        return None
    bands = _column_bands(rows, typical_height)
    if len(bands) < MIN_COLUMNS:
        return None
    if len(rows) > MAX_ROWS or len(bands) > MAX_COLUMNS:
        return None
    if len(rows) * len(bands) > MAX_CELLS:
        return None
    return rows, bands


def _group_is_table(words: list[Word]) -> bool:
    """Ask the shared layout classifier whether merged rows form a table.

    The stored block labels cannot answer this: a PDF often stores one row per
    block, so each block is a paragraph. The merged visual rows are classified
    with the same deterministic rule used for a single block, and only a
    ``table`` label is accepted.
    """
    rows = _cluster_rows(words)
    if len(rows) < MIN_ROWS:
        return False
    heights = [word["height"] for word in words if word["height"] > 0]
    if not heights:
        return False
    line_spans = [
        sorted((word["x"], _right(word)) for word in row) for row in rows
    ]
    text = "\n".join(" ".join(word["text"] for word in row) for row in rows)
    return (
        classify_text_block(
            text,
            max(heights),
            median(heights),
            len(words),
            line_spans=line_spans,
        )
        == "table"
    )


def _blocks_can_join(left, right, typical_height: float) -> bool:
    """Keep a group vertically contiguous; unrelated blocks stay separate."""
    gap = float(right["y"]) - (float(left["y"]) + float(left["height"]))
    limit = max(typical_height * GROUP_GAP_RATIO, MIN_GROUP_GAP)
    return gap <= limit


def _candidate(blocks, rows: list[list[Word]], bands: list[Band]) -> dict[str, Any]:
    return {
        "block_ids": [block["id"] for block in blocks],
        **_grid_payload(rows, bands),
    }


def _cluster_rule_segments(
    segments: list[tuple[float, float, float]],
) -> list[tuple[float, list[Band]]]:
    """Merge parallel rule segments that share a coordinate.

    A cell edge may be drawn once per neighbouring cell, and a long rule may be
    split into pieces. Grouping by coordinate leaves one boundary per real grid
    line while keeping every covered interval, which is what later tells a
    merged cell apart from a drawn separator.
    """
    clusters: list[dict[str, Any]] = []
    for position, start, end in sorted(segments, key=lambda item: item[0]):
        if clusters and position - clusters[-1]["last"] <= RULE_TOLERANCE:
            cluster = clusters[-1]
            cluster["positions"].append(position)
            cluster["last"] = position
            cluster["spans"].append((start, end))
        else:
            clusters.append(
                {
                    "positions": [position],
                    "last": position,
                    "spans": [(start, end)],
                }
            )

    merged: list[tuple[float, list[Band]]] = []
    for cluster in clusters:
        spans: list[Band] = []
        for start, end in sorted(cluster["spans"]):
            if spans and start - spans[-1][1] <= RULE_TOLERANCE:
                spans[-1] = (spans[-1][0], max(spans[-1][1], end))
            else:
                spans.append((start, end))
        centre = sum(cluster["positions"]) / len(cluster["positions"])
        merged.append((centre, spans))
    return merged


def _covers(spans: list[Band], start: float, end: float) -> bool:
    """Return whether one drawn rule crosses the whole band."""
    if end <= start:
        return False
    tolerance = min(RULE_TOLERANCE, (end - start) / 4)
    return any(
        span_start - tolerance <= start and span_end + tolerance >= end
        for span_start, span_end in spans
    )


def _rule_components(
    horizontals: list[tuple[float, float, float]],
    verticals: list[tuple[float, float, float]],
) -> list[
    tuple[
        list[tuple[float, float, float]],
        list[tuple[float, float, float]],
    ]
]:
    """Group rules that touch, so two separate tables stay two candidates."""
    count = len(horizontals) + len(verticals)
    parents = list(range(count))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for horizontal_index, (y, x0, x1) in enumerate(horizontals):
        for vertical_index, (x, y0, y1) in enumerate(verticals):
            if (
                x0 - RULE_TOLERANCE <= x <= x1 + RULE_TOLERANCE
                and y0 - RULE_TOLERANCE <= y <= y1 + RULE_TOLERANCE
            ):
                union(horizontal_index, len(horizontals) + vertical_index)

    groups: dict[int, tuple[list[Any], list[Any]]] = {}
    for index, segment in enumerate(horizontals):
        groups.setdefault(find(index), ([], []))[0].append(segment)
    for index, segment in enumerate(verticals):
        groups.setdefault(find(len(horizontals) + index), ([], []))[1].append(segment)
    return list(groups.values())


def _merged_rectangles(
    horizontal_covered: list[list[bool]],
    vertical_covered: list[list[bool]],
    rows: int,
    columns: int,
) -> tuple[list[tuple[int, int, int, int]], list[list[int]]] | None:
    """Turn missing separators into rectangular merged blocks.

    A separator that is absent in a row joins the two neighbouring columns for
    that row, and a separator absent under a column span joins the rows above
    and below. Every base coordinate must be claimed exactly once and the
    result must be a true rectangle whose outer separators are drawn; anything
    else ``None`` because a stepped shape cannot be inserted faithfully.
    """
    owner: list[list[int]] = [[-1] * columns for _ in range(rows)]
    rectangles: list[tuple[int, int, int, int]] = []

    for row in range(rows):
        for column in range(columns):
            if owner[row][column] != -1:
                continue
            last_column = column
            while (
                last_column + 1 < columns
                and not vertical_covered[last_column + 1][row]
            ):
                last_column += 1
            last_row = row
            changed = True
            while changed:
                changed = False
                if last_row + 1 < rows and not any(
                    horizontal_covered[last_row + 1][index]
                    for index in range(column, last_column + 1)
                ):
                    last_row += 1
                    changed = True
                if last_column + 1 < columns and not any(
                    vertical_covered[last_column + 1][index]
                    for index in range(row, last_row + 1)
                ):
                    last_column += 1
                    changed = True

            # Interior separators must all be absent and the outer ones drawn.
            for inner in range(column + 1, last_column + 1):
                if any(
                    vertical_covered[inner][index]
                    for index in range(row, last_row + 1)
                ):
                    return None
            for inner in range(row + 1, last_row + 1):
                if any(
                    horizontal_covered[inner][index]
                    for index in range(column, last_column + 1)
                ):
                    return None
            if last_column + 1 < columns and not all(
                vertical_covered[last_column + 1][index]
                for index in range(row, last_row + 1)
            ):
                return None
            if last_row + 1 < rows and not all(
                horizontal_covered[last_row + 1][index]
                for index in range(column, last_column + 1)
            ):
                return None

            rectangle_index = len(rectangles)
            for row_index in range(row, last_row + 1):
                for column_index in range(column, last_column + 1):
                    if owner[row_index][column_index] != -1:
                        return None
                    owner[row_index][column_index] = rectangle_index
            rectangles.append((row, column, last_row, last_column))
    return rectangles, owner


def _reline(words: list[Word]) -> list[Word]:
    """Renumber visual lines inside one cell.

    Stored line numbers are block-local, so two blocks can both use line 0. A
    cell that receives words from several blocks would otherwise merge
    unrelated lines. Clustering by vertical centre keeps the source's layout.
    """
    relined: list[Word] = []
    for line_index, line in enumerate(_cluster_rows(words)):
        for word in line:
            relined.append({**word, "line": line_index})
    return relined


def _covered_ratio(box: dict[str, float], container: dict[str, float]) -> float:
    """Share of ``box`` that lies inside ``container``."""
    area = box["width"] * box["height"]
    if area <= 0:
        return 0.0
    left = max(box["x"], container["x"])
    top = max(box["y"], container["y"])
    right = min(box["x"] + box["width"], container["x"] + container["width"])
    bottom = min(box["y"] + box["height"], container["y"] + container["height"])
    if right <= left or bottom <= top:
        return 0.0
    return ((right - left) * (bottom - top)) / area


def _vector_candidates(
    horizontals: list[tuple[float, float, float]],
    verticals: list[tuple[float, float, float]],
    tagged_words: list[tuple[str, Word]],
) -> list[dict[str, Any]]:
    """Build candidates from rules drawn in the PDF, including merged cells.

    Only rule geometry is used, so a span is reported only when the document
    itself omits a separator. Text is assigned by its centre, and a cell with no
    words stays empty rather than borrowing a neighbour's text.
    """
    words = [word for _block_id, word in tagged_words]
    heights = [word["height"] for word in words if word["height"] > 0]
    typical_height = median(heights) if heights else 1.0
    candidates: list[dict[str, Any]] = []

    for component_horizontals, component_verticals in _rule_components(
        horizontals, verticals
    ):
        x_boundaries = _cluster_rule_segments(component_verticals)
        y_boundaries = _cluster_rule_segments(component_horizontals)
        if len(x_boundaries) < MIN_COLUMNS + 1 or len(y_boundaries) < MIN_ROWS + 1:
            continue
        columns = len(x_boundaries) - 1
        rows = len(y_boundaries) - 1
        if rows > MAX_ROWS or columns > MAX_COLUMNS or rows * columns > MAX_CELLS:
            continue

        x_positions = [item[0] for item in x_boundaries]
        y_positions = [item[0] for item in y_boundaries]
        horizontal_covered = [
            [
                _covers(spans, x_positions[column], x_positions[column + 1])
                for column in range(columns)
            ]
            for _position, spans in y_boundaries
        ]
        vertical_covered = [
            [
                _covers(spans, y_positions[row], y_positions[row + 1])
                for row in range(rows)
            ]
            for _position, spans in x_boundaries
        ]

        # Cells must be closed: a chart's axes or a partial rule set would leave
        # an open side, and words beyond it could not be assigned faithfully.
        if not all(horizontal_covered[0]) or not all(horizontal_covered[rows]):
            continue
        if not all(
            vertical_covered[0][row] and vertical_covered[columns][row]
            for row in range(rows)
        ):
            continue

        merged = _merged_rectangles(
            horizontal_covered, vertical_covered, rows, columns
        )
        if merged is None:
            continue
        rectangles, owner = merged

        left = x_positions[0]
        top = y_positions[0]
        right = x_positions[-1]
        bottom = y_positions[-1]
        buckets: list[list[Word]] = [[] for _ in rectangles]
        contributing: dict[str, None] = {}
        for block_id, word in tagged_words:
            centre_x = word["x"] + word["width"] / 2
            centre_y = _centre_y(word)
            if not (left <= centre_x <= right and top <= centre_y <= bottom):
                continue
            column = min(max(bisect_right(x_positions, centre_x) - 1, 0), columns - 1)
            row = min(max(bisect_right(y_positions, centre_y) - 1, 0), rows - 1)
            buckets[owner[row][column]].append(word)
            contributing.setdefault(block_id, None)

        cells: list[dict[str, Any]] = []
        uncertain_cells = 0
        empty_cells = 0
        has_confidence = False
        filled_rows: set[int] = set()
        filled_columns: set[int] = set()
        for index, (row, column, last_row, last_column) in enumerate(rectangles):
            payload = _cell_payload(
                _reline(buckets[index]),
                (x_positions[column], x_positions[last_column + 1]),
                typical_height,
            )
            cells.append(
                {
                    "row": row,
                    "column": column,
                    "rowspan": last_row - row + 1,
                    "colspan": last_column - column + 1,
                    **payload,
                }
            )
            if payload["uncertain"]:
                uncertain_cells += 1
            if payload["empty"]:
                empty_cells += 1
            else:
                filled_rows.update(range(row, last_row + 1))
                filled_columns.update(range(column, last_column + 1))
            if payload["confidence"] is not None:
                has_confidence = True

        filled_cells = len(cells) - empty_cells
        required = max(
            MIN_VECTOR_FILLED_CELLS, ceil(len(cells) * MIN_VECTOR_FILL_RATIO)
        )
        if (
            filled_cells < required
            or len(filled_rows) < MIN_ROWS
            or len(filled_columns) < MIN_COLUMNS
        ):
            continue

        warnings: list[str] = []
        if not has_confidence:
            warnings.append("no_confidence")
        if uncertain_cells:
            warnings.append("low_confidence")
        if empty_cells:
            warnings.append("empty_cells")

        candidates.append(
            {
                "block_ids": list(contributing),
                "rows": rows,
                "columns": columns,
                "has_confidence": has_confidence,
                "uncertain_cells": uncertain_cells,
                "empty_cells": empty_cells,
                "warnings": warnings,
                "source": {
                    "x": round(left, 1),
                    "y": round(top, 1),
                    "width": round(right - left, 1),
                    "height": round(bottom - top, 1),
                },
                "cells": cells,
            }
        )
    return candidates


def _ensure_fresh_run(page, run) -> None:
    """Refuse a proposal when the stored run no longer matches the page."""
    if run is None or run["status"] != "succeeded":
        raise AppError(409, "ocr_not_ready", "OCR has not finished for this page.")
    current_source = page["display_asset_id"] or page["original_asset_id"]
    if (
        run["source_asset_id"] != current_source
        or int(run["rotation"]) != int(page["rotation"])
    ):
        raise AppError(
            409,
            "ocr_stale",
            "The page changed after OCR. Run OCR again before building a table.",
        )


def propose_table(project_dir: Path, page_id: str, block_id: str) -> dict[str, Any]:
    """Return a table proposal for one OCR block.

    Raises a typed :class:`AppError` when the stored result cannot support a
    trustworthy proposal. The caller never receives a half-built grid.
    """
    with project_db(project_dir) as conn:
        page = _page(conn, page_id)
        block = conn.execute(
            "SELECT * FROM ocr_blocks WHERE id = ? AND page_id = ?",
            (block_id, page_id),
        ).fetchone()
        if block is None:
            raise AppError(404, "ocr_block_not_found", "OCR text block not found.")
        run = conn.execute(
            "SELECT * FROM ocr_runs WHERE id = ?", (block["run_id"],)
        ).fetchone()
        _ensure_fresh_run(page, run)
        if block["kind"] != "table":
            raise AppError(
                422,
                "table_block_required",
                "Only a block labelled as a table can produce a table proposal.",
            )
        if int(block["corrected"]):
            raise AppError(
                422,
                "table_source_modified",
                "This block was corrected by hand. Re-run OCR to rebuild its table "
                "from the engine's word positions.",
            )
        words = _parse_words(block["words"])

    if not words:
        raise AppError(
            422,
            "table_no_words",
            "This result has no word positions. Re-run OCR to build a table proposal.",
        )

    heights = [word["height"] for word in words if word["height"] > 0]
    typical_height = median(heights) if heights else 1.0
    rows = _cluster_rows(words)
    if len(rows) < MIN_ROWS:
        raise AppError(
            422,
            "table_not_detected",
            "The stored word positions do not form a table with at least two rows.",
        )

    bands = _column_bands(rows, typical_height)
    if len(bands) < MIN_COLUMNS:
        raise AppError(
            422,
            "table_not_detected",
            "The stored word positions do not form a table with at least two columns.",
        )

    if len(rows) > MAX_ROWS or len(bands) > MAX_COLUMNS:
        raise AppError(
            422,
            "table_too_large",
            f"The proposed table is larger than {MAX_ROWS} rows by {MAX_COLUMNS} columns.",
        )
    if len(rows) * len(bands) > MAX_CELLS:
        raise AppError(
            422,
            "table_too_large",
            f"The proposed table has more than {MAX_CELLS} cells.",
        )

    return _proposal(
        page=page,
        page_id=page_id,
        block_id=block_id,
        run_id=run["id"],
        engine=run["engine"],
        rows=rows,
        bands=bands,
    )


def propose_element_table(
    project_dir: Path,
    element_id: str,
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """Read one saved table crop with the local OCR engine into a proposal.

    The crop is the user's own rectangle, so its kind label already declares the
    intent; this module only checks that the words inside it form a usable grid.
    The image never leaves the device. Every cell keeps the engine's confidence,
    empty cells stay empty, and nothing is written to the element or document.
    """
    with project_db(project_dir) as conn:
        element = conn.execute(
            "SELECT * FROM elements WHERE id = ?", (element_id,)
        ).fetchone()
        if element is None:
            raise AppError(404, "element_not_found", "Region not found.")
        if element["kind"] != "table":
            raise AppError(
                422,
                "table_element_required",
                "Only a saved table region can be read as a table.",
            )
        if not element["asset_id"]:
            raise AppError(
                409,
                "element_has_no_crop",
                "This region has no saved crop image to read.",
            )
        asset = conn.execute(
            "SELECT * FROM assets WHERE id = ?", (element["asset_id"],)
        ).fetchone()
        if asset is None:
            raise AppError(
                409,
                "element_has_no_crop",
                "This region has no saved crop image to read.",
            )
        try:
            image_path = resolve_within(project_dir, asset["relative_path"])
        except ValueError as exc:
            raise AppError(500, "asset_path_invalid", "Asset path is invalid.") from exc
        if not image_path.exists():
            raise AppError(404, "asset_file_missing", "The asset file is missing.")

        page = conn.execute(
            "SELECT width, height FROM pages WHERE id = ?", (element["page_id"],)
        ).fetchone()
        source = {
            "x": float(element["x"]),
            "y": float(element["y"]),
            "width": float(element["width"]),
            "height": float(element["height"]),
        }
        page_width = int(page["width"] or 0) if page else 0
        page_height = int(page["height"] or 0) if page else 0

    # OCR can take seconds. Never hold the SQLite transaction open while the
    # local engine runs.
    content = ocr_service.extract_image_content(image_path, languages or [])

    words = _clean_words(
        [
            word
            for block in content.get("blocks", [])
            for word in block.get("words", [])
        ]
    )
    if not words:
        raise AppError(
            422,
            "table_crop_empty",
            "Local OCR did not find any words in this crop. Check that the region "
            "covers the table and that the OCR language is installed.",
        )

    heights = [word["height"] for word in words if word["height"] > 0]
    typical_height = median(heights) if heights else 1.0
    rows = _cluster_rows(words)
    if len(rows) < MIN_ROWS:
        raise AppError(
            422,
            "table_crop_not_detected",
            "The crop's text does not form a table with at least two rows.",
        )

    bands = _column_bands(rows, typical_height)
    if len(bands) < MIN_COLUMNS:
        raise AppError(
            422,
            "table_crop_not_detected",
            "The crop's text does not form a table with at least two columns.",
        )

    if len(rows) > MAX_ROWS or len(bands) > MAX_COLUMNS:
        raise AppError(
            422,
            "table_too_large",
            f"The proposed table is larger than {MAX_ROWS} rows by {MAX_COLUMNS} columns.",
        )
    if len(rows) * len(bands) > MAX_CELLS:
        raise AppError(
            422,
            "table_too_large",
            f"The proposed table has more than {MAX_CELLS} cells.",
        )

    # Each visual row becomes one grid line, so words from different OCR blocks
    # are joined with a space instead of being stacked by their block-local line
    # number. A cell that wraps onto a second visual line still becomes a second
    # row: the review grid never merges rows it did not observe.
    for row_index, row in enumerate(rows):
        for word in row:
            word["line"] = row_index

    payload = _grid_payload(rows, bands)
    # OCR coordinates are relative to the crop; the review preview positions the
    # box on the page image, so the saved region is the honest source rectangle.
    payload["source"] = source

    return {
        "element_id": element_id,
        "page_id": str(element["page_id"]),
        "engine": content["engine"],
        "engine_version": content["engine_version"],
        "languages": content["languages"],
        "page_width": page_width or None,
        "page_height": page_height or None,
        **payload,
    }


def propose_page_tables(project_dir: Path, page_id: str) -> dict[str, Any]:
    """Find reviewable tables on a page, including cross-block ones.

    Embedded PDF text often stores one block per table row, so no single block
    is labelled ``table``. Consecutive paragraph blocks are merged only when
    their rows share aligned wide gaps, which is the same deterministic test the
    layout classifier applies to one block. A single block already labelled
    ``table`` is also returned, so one dialog can list every table on the page.

    Nothing is saved and no candidate is inserted automatically.
    """
    with project_db(project_dir) as conn:
        page = _page(conn, page_id)
        run = conn.execute(
            "SELECT * FROM ocr_runs WHERE page_id = ? AND status = 'succeeded' "
            "ORDER BY created_at DESC LIMIT 1",
            (page_id,),
        ).fetchone()
        _ensure_fresh_run(page, run)
        blocks = conn.execute(
            "SELECT * FROM ocr_blocks WHERE run_id = ? ORDER BY block_index",
            (run["id"],),
        ).fetchall()
        # Drawn rules are only read from the immutable PDF, so a rotated page or
        # any geometry edit makes them unusable. The word-based detector still
        # works in those cases.
        pdf_source: tuple[Path, int] | None = None
        if (
            page["source_kind"] == "pdf"
            and int(page["rotation"]) == 0
            and page["width"]
            and not edits_service.has_edits(edits_service.decode_edits(page["edits"]))
        ):
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

    eligible: list[tuple[Any, list[Word]]] = []
    for block in blocks:
        words = _parse_words(block["words"])
        if not words:
            continue
        eligible.append((block, words))
    tagged_words = [
        (block["id"], word) for block, words in eligible for word in words
    ]

    heights = [word["height"] for _block, words in eligible for word in words]
    typical_height = median(heights) if heights else 1.0
    candidates: list[dict[str, Any]] = []

    index = 0
    while index < len(eligible) and len(candidates) < MAX_CANDIDATES:
        block, words = eligible[index]
        # A corrected block is a barrier: its stored words no longer describe its
        # text, so a table must not silently bridge across the missing row.
        if int(block["corrected"]):
            index += 1
            continue
        if block["kind"] == "table":
            grid = _build_grid(words)
            if grid is not None:
                candidates.append(_candidate([block], *grid))
            index += 1
            continue
        if block["kind"] != "paragraph":
            index += 1
            continue

        # Extend over vertically contiguous paragraph blocks, then keep the
        # longest prefix that the layout classifier still calls a table.
        end = index
        while end + 1 < len(eligible):
            next_block, _next_words = eligible[end + 1]
            if int(next_block["corrected"]):
                break
            if next_block["kind"] != "paragraph":
                break
            if not _blocks_can_join(eligible[end][0], next_block, typical_height):
                break
            end += 1

        chosen: tuple[int, list[tuple[Any, list[Word]]], Grid] | None = None
        for candidate_end in range(end, index, -1):
            group = eligible[index : candidate_end + 1]
            group_words = [word for _block, words in group for word in words]
            if not _group_is_table(group_words):
                continue
            grid = _build_grid(group_words)
            if grid is None:
                continue
            chosen = (candidate_end, group, grid)
            break

        if chosen is None:
            index += 1
            continue

        candidate_end, group, grid = chosen
        candidates.append(_candidate([item[0] for item in group], *grid))
        index = candidate_end + 1

    vector_candidates: list[dict[str, Any]] = []
    if pdf_source is not None and page["width"]:
        pdf_path, pdf_index = pdf_source
        document = None
        try:
            document = pdf_service.open_document(pdf_path)
        except Exception:
            document = None
        if document is not None:
            try:
                horizontals, verticals = pdf_service.table_lines(
                    document, pdf_index, int(page["width"])
                )
                vector_candidates = _vector_candidates(
                    horizontals, verticals, tagged_words
                )
            finally:
                document.close()

    # A vector grid is exact where it exists, so an OCR candidate that lies
    # inside one is dropped instead of showing the same table twice with a
    # coarser structure and without its merged cells.
    combined = vector_candidates + [
        candidate
        for candidate in candidates
        if not any(
            _covered_ratio(candidate["source"], vector["source"])
            >= VECTOR_COVER_RATIO
            for vector in vector_candidates
        )
    ]
    combined.sort(
        key=lambda candidate: (candidate["source"]["y"], candidate["source"]["x"])
    )

    return {
        "page_id": page_id,
        "run_id": run["id"],
        "engine": run["engine"],
        "page_width": page["width"],
        "page_height": page["height"],
        "candidates": combined[:MAX_CANDIDATES],
    }
