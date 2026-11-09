from __future__ import annotations

import re


def classify_text_block(
    text: str, max_line_height: float, median_line_height: float, word_count: int
) -> str:
    """Conservatively label a text block as a heading, list item or paragraph.

    This is a heuristic used by both OCR and embedded-PDF extraction. It never
    upgrades a block to a table, figure or equation, and callers must keep the
    original text and geometry available for review.
    """
    stripped = text.strip()
    if re.match(r"^(?:\d+[.)]|[•●▪◦·*\-–—])\s+", stripped):
        return "list_item"
    first_line = stripped.splitlines()[0].strip() if stripped else ""
    if (
        max_line_height >= max(1.0, median_line_height * 1.35)
        and word_count <= 14
        and first_line
        and not re.search(r"[.!?;:,]$", first_line)
    ):
        return "heading"
    if first_line and first_line.isupper() and len(first_line) <= 80 and word_count <= 12:
        return "heading"
    return "paragraph"
