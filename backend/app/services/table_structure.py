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
* A page-level detector groups consecutive blocks whose rows share aligned
  columns. This is how embedded PDF text becomes a table when the PDF layer
  stores one block per row. A group is accepted only when the deterministic
  layout classifier that labels single blocks also calls the merged rows a table.

The frontend shows the proposal for review and inserts it only when the user
approves it.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

from app.core.errors import AppError
from app.db.project_schema import project_db
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


def _cell_payload(words: list[Word]) -> dict[str, Any]:
    if not words:
        return {
            "text": "",
            "confidence": None,
            "uncertain": False,
            "empty": True,
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
    }


def _grid_payload(rows: list[list[Word]], bands: list[Band]) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    uncertain_cells = 0
    empty_cells = 0
    has_confidence = False

    for row_index, row in enumerate(rows):
        buckets: list[list[Word]] = [[] for _ in bands]
        for word in row:
            buckets[_best_band(word, bands)].append(word)
        for column_index, bucket in enumerate(buckets):
            cell = _cell_payload(bucket)
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
        "cells": cells,
    }


def _proposal(
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
        page_id=page_id,
        block_id=block_id,
        run_id=run["id"],
        engine=run["engine"],
        rows=rows,
        bands=bands,
    )


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

    eligible: list[tuple[Any, list[Word]]] = []
    for block in blocks:
        words = _parse_words(block["words"])
        if not words:
            continue
        eligible.append((block, words))

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

    return {
        "page_id": page_id,
        "run_id": run["id"],
        "engine": run["engine"],
        "candidates": candidates,
    }
