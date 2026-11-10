from __future__ import annotations

import re

MATH_SYMBOLS = frozenset("=+−-×÷±∑∏∫∮√∞≈≠≤≥<>^_{}[]|")
PAGE_NUMBER_RE = re.compile(
    r"^(?:page\s+)?(?:\d{1,4}|[ivxlcdm]{1,7})[.)]?$",
    re.IGNORECASE,
)
CAPTION_RE = re.compile(
    r"^(?:figure|fig\.?|table|tab\.?|chart|diagram|equation|eq\.?|plate|photo|image)"
    r"\s+(?:[A-Z]?\d+(?:[.\-]\d+)*|[IVXLCDM]+)(?:\s*[:.\)\-–—]|\s*$)",
    re.IGNORECASE,
)
MARGIN_RATIO = 0.08


def _position(
    y: float | None, height: float | None, page_height: float | None
) -> str | None:
    if y is None or height is None or not page_height or page_height <= 0:
        return None
    bottom = y + height
    if y <= page_height * MARGIN_RATIO:
        return "top"
    if bottom >= page_height * (1 - MARGIN_RATIO):
        return "bottom"
    return None


def _is_page_number(text: str) -> bool:
    return bool(PAGE_NUMBER_RE.fullmatch(text.strip()))


def _is_caption(text: str, line_count: int, word_count: int) -> bool:
    if line_count > 3 or word_count > 40:
        return False
    first_line = text.strip().splitlines()[0].strip() if text.strip() else ""
    return bool(first_line and CAPTION_RE.match(first_line))


def _is_equation(text: str, line_count: int) -> bool:
    stripped = text.strip()
    if not stripped or line_count > 2 or len(stripped) > 200:
        return False
    if re.search(r"[.!?;:]$", stripped):
        return False
    compact = "".join(stripped.split())
    if not compact:
        return False
    symbol_count = sum(1 for char in compact if char in MATH_SYMBOLS)
    if symbol_count < 2:
        return False
    if "=" not in compact and symbol_count < 3:
        return False
    return symbol_count / len(compact) >= 0.15


def _looks_like_table(
    line_spans: list[list[tuple[float, float]]], median_line_height: float
) -> bool:
    """Detect a table-like text grid from aligned gaps between words.

    Tesseract usually keeps a text table in one block when its columns are
    close enough. A candidate needs at least two lines with a wide gap in a
    similar horizontal position; ordinary word spacing and single wide gaps
    are ignored.
    """
    if median_line_height <= 0 or len(line_spans) < 2:
        return False

    gap_threshold = max(median_line_height * 1.2, 8.0)
    tolerance = max(median_line_height * 0.75, 6.0)
    gaps_by_line: list[list[float]] = []
    for spans in line_spans:
        ordered = sorted(spans)
        gaps: list[float] = []
        for (_, right), (left, _) in zip(ordered, ordered[1:]):
            gap = left - right
            if gap >= gap_threshold:
                gaps.append((right + left) / 2)
        if gaps:
            gaps_by_line.append(gaps)

    if len(gaps_by_line) < 2:
        return False

    for index, gaps in enumerate(gaps_by_line):
        for other in gaps_by_line[index + 1 :]:
            if any(abs(a - b) <= tolerance for a in gaps for b in other):
                return True
    return False


def classify_text_block(
    text: str,
    max_line_height: float,
    median_line_height: float,
    word_count: int,
    *,
    y: float | None = None,
    height: float | None = None,
    page_height: float | None = None,
    line_spans: list[list[tuple[float, float]]] | None = None,
) -> str:
    """Conservatively label a text block.

    This is a deterministic heuristic used by both OCR and embedded-PDF
    extraction. It never extracts a table or figure structure and never
    changes text; labels are review candidates and the original text and
    geometry stay available. Ambiguous blocks remain paragraphs.
    """
    stripped = text.strip()
    if not stripped:
        return "paragraph"

    line_count = len([line for line in stripped.splitlines() if line.strip()])
    line_count = max(1, line_count)
    position = _position(y, height, page_height)

    if _is_page_number(stripped) and position in {"top", "bottom"}:
        return "page_number"

    if position and line_count == 1 and word_count <= 12:
        if position == "top":
            return "header"
        if position == "bottom":
            return "footer"

    if _is_caption(stripped, line_count, word_count):
        return "caption"

    if _is_equation(stripped, line_count):
        return "equation"

    if line_spans and _looks_like_table(line_spans, median_line_height):
        return "table"

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
