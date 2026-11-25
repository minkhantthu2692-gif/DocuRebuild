"""Deterministic TXT, Markdown, Word and PDF export for the Tiptap document.

The document is stored as Tiptap JSON. This module renders that JSON without
any external service, so export works fully offline. It is intentionally
lossless-first: every text node is preserved and only the presentation is
converted. Content that cannot be represented exactly (for example an
extracted figure stored as a local asset) is written as an explicit marker
instead of being dropped silently.

Markdown output is escaped so extracted text can never become markup: a
heading-like line inside a paragraph stays literal text, and raw HTML is
neutralised. Figure image sources are never included because they are local
API paths that are meaningless outside the app.

Word output embeds the project's own figure images and converts equations to
OMML, so Word can edit them as real equations. Conversion happens locally; the
LaTeX source is kept as a visible fallback if a formula cannot be converted.

PDF output is a fixed A4 layout rendered locally with PyMuPDF's HTML story
engine. Figures are embedded, links become clickable annotations and footnotes
are written as an end-of-document notes list. No offline LaTeX typesetter is
bundled, so equations keep their exact LaTeX source rather than an invented
approximation. Burmese text requires a Unicode Myanmar font on this device.
"""

from __future__ import annotations

import html
import io
import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from xml.sax.saxutils import escape as xml_escape

import latex2mathml.converter
import mathml2omml
import pymupdf
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt
from lxml import etree
from PIL import Image

from app.core.errors import AppError
from app.services import documents, fonts as font_service, pages

ExportFormat = Literal["markdown", "txt", "docx", "pdf"]
TextExportFormat = Literal["markdown", "txt"]

CONTENT_TYPES: dict[ExportFormat, str] = {
    "markdown": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "pdf": "application/pdf",
}
EXTENSIONS: dict[ExportFormat, str] = {
    "markdown": "md",
    "txt": "txt",
    "docx": "docx",
    "pdf": "pdf",
}

_MARKDOWN_SPECIALS = frozenset("\\`*_[]<>")
_SAFE_LINK_PATTERN = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_FIGURE_FALLBACK = "Figure"
_INLINE_IMAGE_FALLBACK = "Image"
# Optional placeholders in a project's page header/footer text. Unknown braces
# stay literal; the text is never rewritten silently.
_LAYOUT_TOKEN_PATTERN = re.compile(r"\{(page|pages|title)\}")
_LAYOUT_PAGE_TOKENS = ("{page}", "{pages}")


def _escape_inline(text: str) -> str:
    return "".join(f"\\{char}" if char in _MARKDOWN_SPECIALS else char for char in text)


def _escape_line_starts(text: str) -> str:
    """Escape markers that would start a block at the beginning of a line."""
    lines: list[str] = []
    for line in text.split("\n"):
        indent = line[: len(line) - len(line.lstrip(" "))]
        rest = line[len(indent) :]
        rest = re.sub(r"^(#{1,6})(?=\s)", r"\\\1", rest)
        rest = re.sub(r"^([-+>])(?=\s)", r"\\\1", rest)
        rest = re.sub(r"^(\d+)([.)])(?=\s)", r"\1\\\2", rest)
        if re.fullmatch(r"-{3,}", rest):
            rest = f"\\{rest}"
        lines.append(indent + rest)
    return "\n".join(lines)


def _code_span(text: str) -> str:
    if not text:
        return ""
    if "`" not in text:
        return f"`{text}`"
    fence = "``"
    while fence in text:
        fence += "`"
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{padding}{text}{padding}{fence}"


def _safe_link(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate or not _SAFE_LINK_PATTERN.match(candidate):
        return None
    if re.search(r"[\s\"'<>]", candidate):
        return None
    return candidate


def _render_marks(text: str, marks: list[dict[str, Any]] | None) -> str:
    if not marks:
        return _escape_inline(text)

    kinds = {str(mark.get("type")): mark for mark in marks if isinstance(mark, dict)}
    href = _safe_link((kinds.get("link") or {}).get("attrs", {}).get("href"))

    # Code spans must not contain Markdown escapes, so they are built from raw
    # text before any escaping happens.
    rendered = _code_span(text) if "code" in kinds else _escape_inline(text)
    if "bold" in kinds:
        rendered = f"**{rendered}**"
    if "italic" in kinds:
        rendered = f"*{rendered}*"
    if "strike" in kinds:
        rendered = f"~~{rendered}~~"
    if "underline" in kinds:
        # Markdown has no underline; inline HTML is the only faithful option.
        rendered = f"<u>{rendered}</u>"
    if "superscript" in kinds:
        # Markdown has no superscript syntax either. Inline HTML preserves the
        # mathematical meaning for renderers that support raw HTML.
        rendered = f"<sup>{rendered}</sup>"
    if "subscript" in kinds:
        rendered = f"<sub>{rendered}</sub>"
    if href:
        rendered = f"[{rendered}]({href})"
    return rendered


def _inline_markdown(nodes: list[dict[str, Any]] | None) -> str:
    if not nodes:
        return ""
    parts: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = node.get("type")
        if kind == "text":
            text = node.get("text")
            if not isinstance(text, str):
                continue
            parts.append(_render_marks(text, node.get("marks")))
        elif kind == "hardBreak":
            parts.append("  \n")
        elif kind == "figure":
            parts.append(_figure_marker(node, markdown=True))
        elif kind == "inlineImage":
            parts.append(_inline_image_marker(node, markdown=True))
        elif kind == "figureReference":
            parts.append(_figure_reference_marker(node))
        elif kind == "equationReference":
            parts.append(_equation_reference_marker(node))
        elif kind == "footnote":
            parts.append(_FOOTNOTE_MARKER_TOKEN)
        elif kind == "inlineMath":
            parts.append(_equation_marker(node, markdown=True, block=False))
        else:
            # Unknown inline node: keep any readable text, never drop content.
            parts.append(_inline_markdown(node.get("content")))
    return "".join(parts)


def _inline_text(nodes: list[dict[str, Any]] | None) -> str:
    if not nodes:
        return ""
    parts: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = node.get("type")
        if kind == "text":
            text = node.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif kind == "hardBreak":
            parts.append("\n")
        elif kind == "figure":
            parts.append(_figure_marker(node, markdown=False))
        elif kind == "inlineImage":
            parts.append(_inline_image_marker(node, markdown=False))
        elif kind == "figureReference":
            parts.append(_figure_reference_marker(node))
        elif kind == "equationReference":
            parts.append(_equation_reference_marker(node))
        elif kind == "footnote":
            parts.append(_FOOTNOTE_MARKER_TOKEN)
        elif kind == "inlineMath":
            parts.append(_equation_marker(node, markdown=False, block=False))
        else:
            parts.append(_inline_text(node.get("content")))
    return "".join(parts)


def _figure_marker(node: dict[str, Any], *, markdown: bool) -> str:
    attrs = node.get("attrs") or {}
    raw_caption = str(attrs.get("caption") or attrs.get("alt") or "").strip()
    caption = raw_caption or _FIGURE_FALLBACK
    numbered = _is_numbered_figure(node)
    if numbered:
        label = f"Figure {_FIGURE_NUMBER_TOKEN}"
        if markdown:
            marker = (
                f"\\[{label}: {_escape_inline(caption)}\\]"
                if raw_caption
                else f"\\[{label}\\]"
            )
        else:
            marker = f"[{label}: {caption}]" if raw_caption else f"[{label}]"
    elif markdown:
        marker = f"\\[Figure: {_escape_inline(caption)}\\]"
    else:
        marker = f"[Figure: {caption}]"
    note = attrs.get("note")
    if isinstance(note, str) and note.strip():
        note_lines = [line for line in note.splitlines() if line.strip()]
        if note_lines:
            if markdown:
                quoted = "\n".join(f"> {_escape_inline(line)}" for line in note_lines)
                marker = f"{marker}  \n{quoted}"
            else:
                marker = f"{marker}\n" + "\n".join(note_lines)
    return marker


def _inline_image_marker(node: dict[str, Any], *, markdown: bool) -> str:
    """A readable marker for a local inline picture outside DOCX/PDF.

    Markdown and plain text cannot reference the project's local API path, so
    the alt text is kept instead of an unusable image link. Nothing is invented.
    """
    attrs = node.get("attrs") or {}
    alt = str(attrs.get("alt") or "").strip() or _INLINE_IMAGE_FALLBACK
    if markdown:
        return f"\\[Image: {_escape_inline(alt)}\\]"
    return f"[Image: {alt}]"


def _equation_latex(node: dict[str, Any]) -> str:
    """Read the stored LaTeX source without altering it."""
    latex = (node.get("attrs") or {}).get("latex")
    return latex.strip() if isinstance(latex, str) else ""


# Numbered display equations get a placeholder during traversal and are numbered
# afterwards in document order. The token cannot collide with prose or LaTeX.
_EQUATION_NUMBER_TOKEN = "\x00equation-number\x00"
# Figures use their own token so equation and figure counters never mix.
_FIGURE_NUMBER_TOKEN = "\x00figure-number\x00"


def _is_numbered_equation(node: dict[str, Any]) -> bool:
    return bool((node.get("attrs") or {}).get("numbered"))


def _is_numbered_figure(node: dict[str, Any]) -> bool:
    return bool((node.get("attrs") or {}).get("numbered"))


def _apply_equation_numbers(rendered: str) -> str:
    """Replace numbered-equation tokens with ``(1)``, ``(2)``, … in order."""
    number = 0
    while _EQUATION_NUMBER_TOKEN in rendered:
        number += 1
        rendered = rendered.replace(_EQUATION_NUMBER_TOKEN, f"({number})", 1)
    return rendered


def _apply_figure_numbers(rendered: str) -> str:
    """Replace numbered-figure tokens with ``1``, ``2``, … in order."""
    number = 0
    while _FIGURE_NUMBER_TOKEN in rendered:
        number += 1
        rendered = rendered.replace(_FIGURE_NUMBER_TOKEN, str(number), 1)
    return rendered


# A cross-reference stores only its target id. The number is resolved from the
# document, so a moved figure renumbers its references and a deleted one becomes
# an explicit marker instead of silently pointing at a different figure.
_FIGURE_REFERENCE_TOKEN = re.compile(r"\x00figure-ref:([^\x00]*)\x00")
_FIGURE_REFERENCE_MISSING = "Figure (missing)"


def _figure_number_map(content: dict[str, Any]) -> dict[str, int]:
    """Map each numbered figure id to its document-order number."""
    numbers: dict[str, int] = {}
    number = 0
    stack: list[dict[str, Any]] = [content]
    while stack:
        node = stack.pop()
        if node.get("type") == "figure" and _is_numbered_figure(node):
            number += 1
            ident = (node.get("attrs") or {}).get("id")
            if isinstance(ident, str) and ident.strip():
                numbers.setdefault(ident.strip(), number)
        children = node.get("content")
        if isinstance(children, list):
            stack.extend(
                child for child in reversed(children) if isinstance(child, dict)
            )
    return numbers


def _figure_reference_marker(node: dict[str, Any]) -> str:
    target = (node.get("attrs") or {}).get("targetId")
    ident = target.strip() if isinstance(target, str) else ""
    return f"\x00figure-ref:{ident}\x00"


def _resolve_figure_references(rendered: str, numbers: dict[str, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        number = numbers.get(match.group(1))
        return f"Figure {number}" if number else _FIGURE_REFERENCE_MISSING

    return _FIGURE_REFERENCE_TOKEN.sub(replace, rendered)


# Equation references follow the same pattern: only the target id is stored, and
# the label is resolved from the document's own numbering.
_EQUATION_REFERENCE_TOKEN = re.compile(r"\x00equation-ref:([^\x00]*)\x00")
_EQUATION_REFERENCE_MISSING = "Equation (missing)"


def _equation_number_map(content: dict[str, Any]) -> dict[str, int]:
    """Map each numbered display equation id to its document-order number."""
    numbers: dict[str, int] = {}
    number = 0
    stack: list[dict[str, Any]] = [content]
    while stack:
        node = stack.pop()
        if node.get("type") == "blockMath" and _is_numbered_equation(node):
            number += 1
            ident = (node.get("attrs") or {}).get("id")
            if isinstance(ident, str) and ident.strip():
                numbers.setdefault(ident.strip(), number)
        children = node.get("content")
        if isinstance(children, list):
            stack.extend(
                child for child in reversed(children) if isinstance(child, dict)
            )
    return numbers


def _equation_reference_marker(node: dict[str, Any]) -> str:
    target = (node.get("attrs") or {}).get("targetId")
    ident = target.strip() if isinstance(target, str) else ""
    return f"\x00equation-ref:{ident}\x00"


def _resolve_equation_references(rendered: str, numbers: dict[str, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        number = numbers.get(match.group(1))
        return f"Equation ({number})" if number else _EQUATION_REFERENCE_MISSING

    return _EQUATION_REFERENCE_TOKEN.sub(replace, rendered)


# Footnotes store their own text on an inline atom. The visible number is derived
# from document order, so inserting or deleting a note renumbers the rest. Every
# footnote is counted, even one with empty text, so the marker and its definition
# can never drift apart.
_FOOTNOTE_MARKER_TOKEN = "\x00footnote-marker\x00"


def _footnote_nodes(content: dict[str, Any]) -> list[str]:
    """Read footnote text in document order."""
    notes: list[str] = []
    stack: list[dict[str, Any]] = [content]
    while stack:
        node = stack.pop()
        if node.get("type") == "footnote":
            text = (node.get("attrs") or {}).get("text")
            notes.append(text if isinstance(text, str) else "")
        children = node.get("content")
        if isinstance(children, list):
            stack.extend(
                child for child in reversed(children) if isinstance(child, dict)
            )
    return notes


def _apply_footnote_numbers(rendered: str, *, markdown: bool) -> str:
    """Replace footnote tokens with ``[^n]`` (Markdown) or ``[n]`` (text)."""
    number = 0
    while _FOOTNOTE_MARKER_TOKEN in rendered:
        number += 1
        marker = f"[^{number}]" if markdown else f"[{number}]"
        rendered = rendered.replace(_FOOTNOTE_MARKER_TOKEN, marker, 1)
    return rendered


def _footnote_definitions_markdown(notes: list[str]) -> str:
    """Write GitHub-flavoured footnote definitions in numbering order."""
    definitions: list[str] = []
    for index, text in enumerate(notes, start=1):
        lines = text.splitlines() or [""]
        # Note text is literal: escape markup characters so a note cannot become
        # document structure or inject another footnote marker.
        definitions.append(f"[^{index}]: {_escape_inline(lines[0])}".rstrip())
        # A continuation line must be indented, or it would end the definition.
        definitions.extend(f"    {_escape_inline(line)}" for line in lines[1:])
    return "\n".join(definitions)


def _footnote_notes_text(notes: list[str]) -> str:
    """Readable notes section for plain text, matching the editor's preview."""
    if not notes:
        return ""
    lines = [f"[{index}] {text}" for index, text in enumerate(notes, start=1)]
    return "Notes:\n" + "\n".join(lines)


def _equation_marker(node: dict[str, Any], *, markdown: bool, block: bool) -> str:
    latex = _equation_latex(node)
    if not latex:
        return ""
    if not markdown:
        # Plain text keeps the exact LaTeX source the user typed.
        marker = latex
    else:
        # Math must never be escaped as prose, or its backslashes break.
        marker = f"$$\n{latex}\n$$" if block else f"${latex}$"
    if block and _is_numbered_equation(node):
        marker = f"{marker} {_EQUATION_NUMBER_TOKEN}"
    return marker


def _cell_parts(node: dict[str, Any], *, markdown: bool) -> list[str]:
    """Readable content of one table cell, block by block.

    A cell can hold more than one paragraph. Every block is kept; nothing is
    dropped because a Markdown table cell can only express inline content.
    """
    parts: list[str] = []
    for child in node.get("content") or []:
        if not isinstance(child, dict):
            continue
        kind = child.get("type")
        if kind in {"paragraph", "heading"}:
            rendered = (
                _inline_markdown(child.get("content"))
                if markdown
                else _inline_text(child.get("content"))
            )
        else:
            rendered = (
                _block_markdown(child) if markdown else _block_text(child)
            )
        parts.append(rendered.strip("\n") if rendered else "")
    return [part for part in parts if part]


def _cell_span(cell: dict[str, Any], name: str) -> int:
    attrs = cell.get("attrs") or {}
    try:
        value = int(attrs.get(name) or 1)
    except (TypeError, ValueError):
        return 1
    return max(value, 1)


def _table_rows(node: dict[str, Any]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for row in node.get("content") or []:
        if not isinstance(row, dict) or row.get("type") != "tableRow":
            continue
        cells = [
            cell
            for cell in (row.get("content") or [])
            if isinstance(cell, dict)
            and cell.get("type") in {"tableCell", "tableHeader"}
        ]
        if cells:
            rows.append(cells)
    return rows


def _table_has_spans(rows: list[list[dict[str, Any]]]) -> bool:
    return any(
        _cell_span(cell, "colspan") > 1 or _cell_span(cell, "rowspan") > 1
        for row in rows
        for cell in row
    )


def _table_header_row(rows: list[list[dict[str, Any]]]) -> bool:
    if not rows:
        return False
    first = rows[0]
    return bool(first) and all(
        cell.get("type") == "tableHeader" for cell in first
    )


def _table_html(rows: list[list[dict[str, Any]]]) -> str:
    """Faithful fallback for merged cells.

    GFM tables cannot express ``colspan``/``rowspan``. Rendering HTML keeps the
    exact cell structure instead of duplicating or dropping merged content.
    """
    lines = ["<table>"]
    for row in rows:
        lines.append("  <tr>")
        for cell in row:
            tag = "th" if cell.get("type") == "tableHeader" else "td"
            attributes = ""
            for name in ("colspan", "rowspan"):
                span = _cell_span(cell, name)
                if span > 1:
                    attributes += f' {name}="{span}"'
            parts = _cell_parts(cell, markdown=False)
            text = "<br>".join(html.escape(part, quote=False) for part in parts)
            lines.append(f"    <{tag}{attributes}>{text}</{tag}>")
        lines.append("  </tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _table_markdown(node: dict[str, Any]) -> str:
    rows = _table_rows(node)
    if not rows:
        return ""
    if _table_has_spans(rows):
        return _table_html(rows)

    columns = max(len(row) for row in rows)
    header = _table_header_row(rows)
    body = rows[1:] if header else rows

    def render_row(row: list[dict[str, Any]]) -> str:
        cells: list[str] = []
        for cell in row:
            parts = _cell_parts(cell, markdown=True)
            text = "<br>".join(parts).replace("\n", "<br>")
            # A literal pipe would split the cell into two columns.
            cells.append(text.replace("|", r"\|"))
        cells.extend([""] * (columns - len(cells)))
        return f"| {' | '.join(cells)} |"

    # GFM requires a header row. If the table has none, an empty structural
    # header is added; the real first row stays a data row.
    header_cells = (
        [_render_header_cell(cell) for cell in rows[0]]
        if header
        else [""] * columns
    )
    header_line = f"| {' | '.join(header_cells)} |"
    separator = f"| {' | '.join('---' for _ in range(columns))} |"
    body_lines = [render_row(row) for row in body]
    return "\n".join([header_line, separator, *body_lines])


def _render_header_cell(cell: dict[str, Any]) -> str:
    parts = _cell_parts(cell, markdown=True)
    # Header cells obey the same escaping as body cells.
    return "<br>".join(parts).replace("\n", "<br>").replace("|", r"\|")


def _table_text(node: dict[str, Any]) -> str:
    rows = _table_rows(node)
    if not rows:
        return ""
    columns = max(len(row) for row in rows)
    header = _table_header_row(rows)
    lines: list[str] = []
    for index, row in enumerate(rows):
        cells = [" ".join(_cell_parts(cell, markdown=False)) for cell in row]
        cells.extend([""] * (columns - len(cells)))
        lines.append(" | ".join(cells))
        if header and index == 0:
            lines.append(" | ".join("---" for _ in range(columns)))
    return "\n".join(lines)


def _block_markdown(node: dict[str, Any], depth: int = 0) -> str:
    kind = node.get("type")
    children = node.get("content") or []

    if kind == "paragraph":
        return _escape_line_starts(_inline_markdown(children)).strip()
    if kind == "heading":
        level = node.get("attrs", {}).get("level", 1)
        try:
            level = min(max(int(level), 1), 6)
        except (TypeError, ValueError):
            level = 1
        text = _escape_line_starts(_inline_markdown(children)).strip()
        return f"{'#' * level} {text}".rstrip()
    if kind == "bulletList":
        items = [_list_item(item, "-", depth) for item in children]
        return "\n".join(item for item in items if item)
    if kind == "orderedList":
        start = node.get("attrs", {}).get("start", 1)
        try:
            start = int(start)
        except (TypeError, ValueError):
            start = 1
        items = [
            _list_item(item, f"{start + index}.", depth)
            for index, item in enumerate(children)
        ]
        return "\n".join(item for item in items if item)
    if kind == "blockquote":
        inner = _blocks_markdown(children, depth)
        if not inner:
            return ""
        return "\n".join(">" if not line else f"> {line}" for line in inner.split("\n"))
    if kind == "codeBlock":
        raw_language = str((node.get("attrs") or {}).get("language") or "")
        language = re.sub(r"[^A-Za-z0-9+#._-]", "", raw_language)
        code = _inline_text(children)
        fence = "```"
        while fence in code:
            fence += "`"
        return f"{fence}{language}\n{code}\n{fence}"
    if kind == "horizontalRule":
        return "---"
    if kind == "figure":
        return _figure_marker(node, markdown=True)
    if kind == "inlineImage":
        return _inline_image_marker(node, markdown=True)
    if kind == "blockMath":
        return _equation_marker(node, markdown=True, block=True)
    if kind == "table":
        return _table_markdown(node)
    if kind == "hardBreak":
        return ""
    return _blocks_markdown(children, depth)


def _list_item(node: dict[str, Any], marker: str, depth: int) -> str:
    if not isinstance(node, dict):
        return ""
    inner = _blocks_markdown(node.get("content") or [], depth + 1)
    if not inner:
        return marker
    lines = inner.split("\n")
    padding = " " * (len(marker) + 1)
    first = f"{marker} {lines[0]}"
    continuation = [f"{padding}{line}" if line else "" for line in lines[1:]]
    return "\n".join([first, *continuation])


def _blocks_markdown(nodes: list[dict[str, Any]], depth: int = 0) -> str:
    blocks: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        rendered = _block_markdown(node, depth)
        if rendered:
            blocks.append(rendered)
    return "\n\n".join(blocks)


def _block_text(node: dict[str, Any]) -> str:
    kind = node.get("type")
    children = node.get("content") or []

    if kind in {"paragraph", "heading"}:
        return _inline_text(children).strip()
    if kind in {"bulletList", "orderedList"}:
        start = 1
        if kind == "orderedList":
            try:
                start = int((node.get("attrs") or {}).get("start", 1))
            except (TypeError, ValueError):
                start = 1
        items: list[str] = []
        for index, item in enumerate(children, start=start):
            if not isinstance(item, dict):
                continue
            marker = "-" if kind == "bulletList" else f"{index}."
            inner = _blocks_text(item.get("content") or [])
            inner_lines = inner.split("\n") if inner else [""]
            padding = " " * (len(marker) + 1)
            lines = [f"{marker} {inner_lines[0]}"]
            lines.extend(f"{padding}{line}" if line else "" for line in inner_lines[1:])
            items.append("\n".join(lines))
        return "\n".join(items)
    if kind == "blockquote":
        inner = _blocks_text(children)
        return inner
    if kind == "codeBlock":
        return _inline_text(children)
    if kind == "horizontalRule":
        return "-" * 3
    if kind == "figure":
        return _figure_marker(node, markdown=False)
    if kind == "inlineImage":
        return _inline_image_marker(node, markdown=False)
    if kind == "blockMath":
        return _equation_marker(node, markdown=False, block=True)
    if kind == "table":
        return _table_text(node)
    if kind == "hardBreak":
        return ""
    return _blocks_text(children)


def _blocks_text(nodes: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        rendered = _block_text(node).strip("\n")
        if rendered.strip():
            blocks.append(rendered)
    return "\n\n".join(blocks)


def render_markdown(content: dict[str, Any]) -> str:
    """Render a Tiptap document as Markdown, ending with a single newline."""
    figure_numbers = _figure_number_map(content)
    equation_numbers = _equation_number_map(content)
    notes = _footnote_nodes(content)
    body = _apply_footnote_numbers(
        _resolve_equation_references(
            _resolve_figure_references(
                _apply_figure_numbers(
                    _apply_equation_numbers(
                        _blocks_markdown(content.get("content") or [])
                    )
                ),
                figure_numbers,
            ),
            equation_numbers,
        ),
        markdown=True,
    )
    if notes:
        definitions = _footnote_definitions_markdown(notes)
        body = f"{body}\n\n{definitions}" if body else definitions
    return f"{body}\n" if body else ""


def render_text(content: dict[str, Any]) -> str:
    """Render a Tiptap document as plain text, ending with a single newline."""
    figure_numbers = _figure_number_map(content)
    equation_numbers = _equation_number_map(content)
    notes = _footnote_nodes(content)
    body = _apply_footnote_numbers(
        _resolve_equation_references(
            _resolve_figure_references(
                _apply_figure_numbers(
                    _apply_equation_numbers(_blocks_text(content.get("content") or []))
                ),
                figure_numbers,
            ),
            equation_numbers,
        ),
        markdown=False,
    )
    if notes:
        notes_text = _footnote_notes_text(notes)
        body = f"{body}\n\n{notes_text}" if body else notes_text
    return f"{body}\n" if body else ""


def render(content: dict[str, Any], fmt: TextExportFormat) -> str:
    return render_markdown(content) if fmt == "markdown" else render_text(content)


def safe_filename(name: str, fmt: ExportFormat) -> str:
    """Build a portable ASCII download name from the project name."""
    cleaned = _UNSAFE_FILENAME.sub("-", name.strip()).strip("-._")
    cleaned = cleaned[:80].strip("-._") or "document"
    return f"{cleaned}.{EXTENSIONS[fmt]}"


def download_filename(name: str, fmt: ExportFormat) -> str:
    """Build a Unicode-preserving download name (Burmese project names)."""
    cleaned = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]+', "-", name.strip())
    cleaned = cleaned.strip(" .-_")[:80].strip(" .-_") or "document"
    return f"{cleaned}.{EXTENSIONS[fmt]}"


# --- Word (.docx) export -------------------------------------------------

# Figure sources are local API paths such as
# /api/projects/<id>/assets/<asset-id>/file?v=... The asset id is resolved
# against this project's own database, so a document can never pull an image
# from another project or from the filesystem.
_ASSET_SRC = re.compile(r"/assets/([0-9A-Fa-f-]{36})/file")
_MAX_IMAGE_WIDTH = Inches(6.0)
# An inline picture shares a line with prose, so it is capped in both directions
# instead of taking over the page.
_MAX_INLINE_IMAGE_WIDTH = Inches(2.2)
_MAX_INLINE_IMAGE_HEIGHT = Inches(1.4)
_ALIGNMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}
_LIST_TYPES = frozenset({"bulletList", "orderedList"})


def _int_attr(node: dict[str, Any], name: str, default: int) -> int:
    value = (node.get("attrs") or {}).get(name)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _span_attr(value: Any, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 1
    return max(1, min(number, maximum))


def _footnote_xml(notes: list[str]) -> bytes:
    """Build the ``word/footnotes.xml`` part for the given notes.

    Word requires the two separator notes (ids -1 and 0) before real footnotes.
    Every note text is XML-escaped, and a newline becomes a real line break so a
    multi-line note is not silently collapsed.
    """
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f"<w:footnotes {nsdecls('w')}>",
        (
            '  <w:footnote w:type="separator" w:id="-1">'
            '<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
            "<w:r><w:separator/></w:r></w:p></w:footnote>"
        ),
        (
            '  <w:footnote w:type="continuationSeparator" w:id="0">'
            '<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
            "<w:r><w:continuationSeparator/></w:r></w:p></w:footnote>"
        ),
    ]
    for index, text in enumerate(notes, start=1):
        lines = text.splitlines() or [""]
        # The first line keeps a leading space after the generated note number.
        first, *rest = lines
        body = f'<w:t xml:space="preserve"> {xml_escape(first)}</w:t>'
        for line in rest:
            body += f'<w:br/><w:t xml:space="preserve">{xml_escape(line)}</w:t>'
        parts.append(
            f'  <w:footnote w:id="{index}">'
            '<w:p><w:pPr><w:pStyle w:val="FootnoteText"/></w:pPr>'
            '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr>'
            "<w:footnoteRef/></w:r>"
            f"<w:r>{body}</w:r></w:p></w:footnote>"
        )
    parts.append("</w:footnotes>")
    return "\n".join(parts).encode("utf-8")


def _ensure_footnote_styles(document: Any) -> None:
    """Add the two footnote styles Word expects, without duplicating them."""
    existing = {style.name for style in document.styles}
    if "Footnote Reference" not in existing:
        style = document.styles.add_style("Footnote Reference", WD_STYLE_TYPE.CHARACTER)
        style.font.superscript = True
    if "Footnote Text" not in existing:
        document.styles.add_style("Footnote Text", WD_STYLE_TYPE.PARAGRAPH)


def _attach_footnotes(document: Any, notes: list[str]) -> None:
    """Attach a real footnotes part so Word shows native footnotes."""
    if not notes:
        return
    _ensure_footnote_styles(document)
    part = Part(
        PackURI("/word/footnotes.xml"),
        CT.WML_FOOTNOTES,
        _footnote_xml(notes),
        document.part.package,
    )
    document.part.relate_to(part, RT.FOOTNOTES)


# --- Word typography ----------------------------------------------------

_DOCX_FONT_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
)
_DOCX_OBFUSCATED_FONT_TYPE = (
    "application/vnd.openxmlformats-officedocument.obfuscatedFont"
)
# Word embeds at most these four faces for one family.
_DOCX_FONT_VARIANTS = (
    ("embedRegular", False, 400),
    ("embedBold", False, 700),
    ("embedItalic", True, 400),
    ("embedBoldItalic", True, 700),
)
# A document with many families must not become a multi-hundred-megabyte file.
_DOCX_MAX_EMBEDDED_BYTES = 48 * 1024 * 1024


def _docx_font_family(marks: dict[str, Any]) -> str:
    text_style = marks.get("textStyle")
    if not isinstance(text_style, dict):
        return ""
    return font_service.sanitize_family(text_style.get("fontFamily"))


def _docx_fonts_element(properties: Any, family: str) -> Any:
    """Create a ``w:rFonts`` element that applies to every script in the run."""
    fonts = OxmlElement("w:rFonts")
    for attribute in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attribute), family)
    properties.append(fonts)
    return fonts


def _docx_apply_font_family(run: Any, marks: dict[str, Any]) -> None:
    family = _docx_font_family(marks)
    if not family:
        return
    run.font.name = family
    properties = run._element.get_or_add_rPr()
    fonts = properties.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        properties.insert(0, fonts)
    for attribute in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attribute), family)


def _closest_face(
    faces: list[Any], *, italic: bool, weight: int
) -> Any | None:
    """Pick the face matching a style axis, allowing a non-standard weight."""
    candidates = [face for face in faces if face.italic == italic]
    if not candidates:
        return None
    return min(candidates, key=lambda face: abs(face.weight - weight))


def _docx_obfuscate_font(data: bytes, font_key: str) -> bytes:
    """Apply Word's embedded-font obfuscation to the first 32 bytes."""
    key = bytes.fromhex(font_key.replace("-", ""))
    mask = key[::-1] * 2
    result = bytearray(data)
    for index in range(min(32, len(result))):
        result[index] ^= mask[index]
    return bytes(result)


def _docx_font_table(document: Any) -> Any | None:
    for part in document.part.package.iter_parts():
        if str(part.partname) == "/word/fontTable.xml":
            return part
    return None


def _docx_font_entry(root: Any, family: str) -> Any:
    """Return the existing ``w:font`` entry for a family, or add one."""
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for entry in root.findall(f"{namespace}font"):
        if (entry.get(f"{namespace}name") or "").casefold() == family.casefold():
            return entry
    entry = etree.SubElement(root, f"{namespace}font")
    entry.set(f"{namespace}name", family)
    for tag, value in (("charset", "00"), ("family", "auto"), ("pitch", "variable")):
        child = etree.SubElement(entry, f"{namespace}{tag}")
        child.set(f"{namespace}val", value)
    return entry


def _docx_enable_font_embedding(document: Any) -> None:
    settings = document.settings.element
    if settings.find(qn("w:embedTrueTypeFonts")) is not None:
        return
    element = OxmlElement("w:embedTrueTypeFonts")
    zoom = settings.find(qn("w:zoom"))
    if zoom is not None:
        zoom.addnext(element)
    else:
        settings.insert(0, element)


def _embed_docx_fonts(document: Any, content: dict[str, Any], session: Any) -> None:
    """Add the used local font faces to a Word package.

    Word reads embedded faces from ``word/fonts/*.odttf``, linked from
    ``fontTable.xml`` and obfuscated with the per-font GUID. Only faces whose
    licence allows embedding are copied, so an export never bypasses ``fsType``.
    """
    families = font_service.export_faces_for_document(content, session)
    if not families:
        return
    font_table = _docx_font_table(document)
    if font_table is None:
        return
    root = etree.fromstring(font_table.blob)
    embedded = 0
    total = 0
    seen_faces: set[tuple[str, int]] = set()
    for faces in families.values():
        family = faces[0].family
        entry = None
        for tag, italic, weight in _DOCX_FONT_VARIANTS:
            face = _closest_face(faces, italic=italic, weight=weight)
            if face is None or not font_service.embedding_allowed(face):
                continue
            identity = (str(face.path), face.index)
            if identity in seen_faces:
                continue
            data = font_service.face_bytes(face)
            if not data:
                continue
            if total + len(data) > _DOCX_MAX_EMBEDDED_BYTES:
                break
            seen_faces.add(identity)
            font_key = str(uuid.uuid4()).upper()
            embedded += 1
            part = Part(
                PackURI(f"/word/fonts/font{embedded}.odttf"),
                _DOCX_OBFUSCATED_FONT_TYPE,
                _docx_obfuscate_font(data, font_key),
                document.part.package,
            )
            relationship_id = font_table.relate_to(part, _DOCX_FONT_RELATIONSHIP)
            if entry is None:
                entry = _docx_font_entry(root, family)
            child = etree.SubElement(entry, qn(f"w:{tag}"))
            child.set(qn("r:id"), relationship_id)
            child.set(qn("w:fontKey"), "{" + font_key + "}")
            total += len(data)
    if not embedded:
        return
    _docx_enable_font_embedding(document)
    font_table._blob = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )


_EQUATION_ARRAY_ENVIRONMENTS = (
    "alignedat",
    "aligned",
    "alignat*",
    "alignat",
    "align*",
    "align",
    "flalign*",
    "flalign",
    "gather*",
    "gather",
    "multline*",
    "multline",
    "split",
    "eqnarray*",
    "eqnarray",
)
# Longest first keeps names that share a prefix (`align`/`aligned`,
# `alignat`/`alignat*`) unambiguous to read; the required `}` already
# prevents a short name from matching a longer environment.
_EQUATION_ARRAY_BEGIN = re.compile(
    r"^\s*(?:\\displaystyle\s*)?\\begin\{("
    + "|".join(
        re.escape(name)
        for name in sorted(_EQUATION_ARRAY_ENVIRONMENTS, key=len, reverse=True)
    )
    + r")\}"
)
_EQUATION_ARRAY_ANYWHERE = re.compile(
    r"\\begin\{("
    + "|".join(
        re.escape(name)
        for name in sorted(_EQUATION_ARRAY_ENVIRONMENTS, key=len, reverse=True)
    )
    + r")\}"
)


def _split_equation_body(body: str) -> list[list[str]]:
    """Split an aligned/array environment into rows of cells.

    A ``\\\\`` outside braces and nested environments starts a new row, and a bare
    ``&`` starts a new cell. Escaped braces and ``\\&`` stay literal, and nested
    matrices keep their own row and column separators.
    """
    rows: list[list[str]] = []
    cells: list[str] = []
    current: list[str] = []
    brace_depth = 0
    environment_depth = 0
    index = 0
    length = len(body)

    while index < length:
        if (
            body.startswith("\\\\", index)
            and brace_depth == 0
            and environment_depth == 0
        ):
            cells.append("".join(current))
            rows.append(cells)
            cells = []
            current = []
            index += 2
            # LaTeX allows optional row spacing after the separator.
            spacing = re.match(r"\[[^\]]*\]", body[index:])
            if spacing is not None:
                index += spacing.end()
            continue

        char = body[index]
        if char == "\\":
            if body.startswith("\\&", index):
                current.append("\\&")
                index += 2
                continue
            if body.startswith("\\begin{", index) or body.startswith("\\end{", index):
                closing = body.find("}", index)
                if closing != -1:
                    if body.startswith("\\begin{", index):
                        environment_depth += 1
                    else:
                        environment_depth = max(0, environment_depth - 1)
                    current.append(body[index : closing + 1])
                    index = closing + 1
                    continue
            if index + 1 < length and body[index + 1] in "{}":
                current.append(body[index : index + 2])
                index += 2
                continue
            current.append(char)
            index += 1
            continue

        if char == "&" and brace_depth == 0 and environment_depth == 0:
            cells.append("".join(current))
            current = []
            index += 1
            continue

        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth = max(0, brace_depth - 1)
        current.append(char)
        index += 1

    cells.append("".join(current))
    rows.append(cells)
    # A trailing row separator leaves one empty row; LaTeX does not render it.
    if len(rows) > 1 and all(not cell.strip() for cell in rows[-1]):
        rows.pop()
    return rows


def _equation_cell_omml(cell: str) -> str | None:
    """Convert one alignment cell to the inner XML of a Word math element."""
    source = cell.strip()
    if not source:
        return ""
    try:
        mathml = latex2mathml.converter.convert(source)
        omml = mathml2omml.convert(mathml)
    except Exception:
        return None
    if not omml or not omml.startswith("<m:oMath") or not omml.endswith("</m:oMath>"):
        return None
    return omml[omml.index(">") + 1 : -len("</m:oMath>")]


def _equation_array_omml(latex: str) -> tuple[bool, str | None]:
    """Convert ``aligned``/``align``/``gather`` style environments to OMML.

    Returns ``(detected, source)``. ``detected`` is true when the source is an
    equation array, even if it could not be converted, so the caller does not fall
    back to a converter that would invent per-row numbers. A one-column array
    becomes a Word equation array; alignment points become right/left matrix
    columns, which preserve the layout without dropping any symbol.
    """
    match = _EQUATION_ARRAY_BEGIN.match(latex)
    if match is None:
        return False, None
    environment = match.group(1)
    end_marker = f"\\end{{{environment}}}"
    text = latex.strip()
    if not text.endswith(end_marker):
        return False, None
    body = text[match.end() : -len(end_marker)]
    if environment in ("alignedat", "alignat", "alignat*"):
        # These environments require a column-pair count, e.g. {2}.
        body = re.sub(r"^\s*\{\s*\d+\s*\}", "", body)
    # A nested array environment would need recursive layout; keep the exact
    # LaTeX fallback instead of emitting a half-converted equation.
    if _EQUATION_ARRAY_ANYWHERE.search(body):
        return True, None

    rows = _split_equation_body(body)
    converted: list[list[str]] = []
    for row in rows:
        cells: list[str] = []
        for cell in row:
            omml = _equation_cell_omml(cell)
            if omml is None:
                return True, None
            cells.append(omml)
        converted.append(cells or [""])

    width = max(len(row) for row in converted)
    if width == 1:
        if len(converted) == 1:
            return True, f"<m:oMath>{converted[0][0]}</m:oMath>"
        body_rows = "".join(f"<m:e>{row[0]}</m:e>" for row in converted)
        return True, f"<m:oMath><m:eqArr>{body_rows}</m:eqArr></m:oMath>"

    columns = "".join(
        '<m:mc><m:mcPr><m:count m:val="1"/><m:mcJc m:val="{}"/></m:mcPr></m:mc>'.format(
            "right" if column % 2 == 0 else "left"
        )
        for column in range(width)
    )
    matrix_rows = []
    for row in converted:
        padded = row + [""] * (width - len(row))
        cells = "".join(f"<m:e>{cell}</m:e>" for cell in padded)
        matrix_rows.append(f"<m:mr>{cells}</m:mr>")
    return True, (
        "<m:oMath><m:m><m:mPr><m:mcs>"
        f"{columns}"
        "</m:mcs></m:mPr>"
        + "".join(matrix_rows)
        + "</m:m></m:oMath>"
    )


class _DocxRenderer:
    """Turn the stored Tiptap JSON into native Word content."""

    def __init__(self, document: Any, project_dir: Path) -> None:
        self.document = document
        self.project_dir = project_dir
        self.equation_number = 0
        self.figure_number = 0
        self.figure_numbers: dict[str, int] = {}
        self.equation_numbers: dict[str, int] = {}
        self.footnotes: list[str] = []
        self._omml_cache: dict[str, str | None] = {}

    # -- equations -----------------------------------------------------

    def _omml(self, latex: str) -> str | None:
        if latex in self._omml_cache:
            return self._omml_cache[latex]
        detected, array_source = _equation_array_omml(latex)
        if detected:
            source = array_source
        else:
            try:
                mathml = latex2mathml.converter.convert(latex)
                source = mathml2omml.convert(mathml)
            except Exception:
                # A formula that cannot be converted keeps its LaTeX below.
                source = None
        self._omml_cache[latex] = source
        return source

    def _add_math(self, paragraph: Any, latex: str) -> bool:
        source = self._omml(latex)
        if not source:
            return False
        try:
            element = parse_xml(f"<root {nsdecls('m')}>{source}</root>")[0]
        except Exception:
            return False
        paragraph._p.append(element)
        return True

    def _block_math(self, container: Any, node: dict[str, Any]) -> None:
        latex = _equation_latex(node)
        if not latex:
            return
        paragraph = container.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if not self._add_math(paragraph, latex):
            run = paragraph.add_run(latex)
            run.italic = True
        if _is_numbered_equation(node):
            self.equation_number += 1
            paragraph.add_run(f" ({self.equation_number})")

    # -- inline content -------------------------------------------------

    def _style_run(self, run: Any, marks: dict[str, Any]) -> None:
        if "bold" in marks:
            run.bold = True
        if "italic" in marks:
            run.italic = True
        if "strike" in marks:
            run.font.strike = True
        if "underline" in marks:
            run.underline = True
        if "code" in marks:
            run.font.name = "Consolas"
            run.font.size = Pt(10)
        else:
            _docx_apply_font_family(run, marks)
        if "superscript" in marks:
            run.font.superscript = True
        elif "subscript" in marks:
            run.font.subscript = True

    def _add_hyperlink(
        self, paragraph: Any, text: str, url: str, marks: dict[str, Any]
    ) -> None:
        relationship_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), relationship_id)
        run = OxmlElement("w:r")
        properties = OxmlElement("w:rPr")
        family = _docx_font_family(marks)
        if family:
            _docx_fonts_element(properties, family)
        if "bold" in marks:
            properties.append(OxmlElement("w:b"))
        if "italic" in marks:
            properties.append(OxmlElement("w:i"))
        if "strike" in marks:
            properties.append(OxmlElement("w:strike"))
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "0563C1")
        properties.append(color)
        underline = OxmlElement("w:u")
        underline.set(qn("w:val"), "single")
        properties.append(underline)
        if "superscript" in marks:
            vertical = OxmlElement("w:vertAlign")
            vertical.set(qn("w:val"), "superscript")
            properties.append(vertical)
        elif "subscript" in marks:
            vertical = OxmlElement("w:vertAlign")
            vertical.set(qn("w:val"), "subscript")
            properties.append(vertical)
        run.append(properties)
        value = OxmlElement("w:t")
        value.text = text
        value.set(qn("xml:space"), "preserve")
        run.append(value)
        hyperlink.append(run)
        paragraph._p.append(hyperlink)

    def _add_inline(self, paragraph: Any, nodes: list[dict[str, Any]] | None) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            kind = node.get("type")
            if kind == "text":
                text = node.get("text")
                if not isinstance(text, str):
                    continue
                marks = {
                    str(mark.get("type")): (mark.get("attrs") or {})
                    for mark in node.get("marks") or []
                    if isinstance(mark, dict)
                }
                href = _safe_link((marks.get("link") or {}).get("href"))
                if href:
                    self._add_hyperlink(paragraph, text, href, marks)
                else:
                    run = paragraph.add_run(text)
                    self._style_run(run, marks)
            elif kind == "inlineMath":
                latex = _equation_latex(node)
                if latex and not self._add_math(paragraph, latex):
                    paragraph.add_run(latex).italic = True
            elif kind == "inlineImage":
                self._add_inline_image(paragraph, node)
            elif kind == "hardBreak":
                paragraph.add_run().add_break()
            elif kind == "figure":
                # A figure inside a sentence has no place in Word's flow; keep
                # its caption so no information disappears.
                attrs = node.get("attrs") or {}
                caption = attrs.get("caption") or attrs.get("alt") or _FIGURE_FALLBACK
                paragraph.add_run(f"[Figure: {caption}]")
            elif kind == "figureReference":
                target = (node.get("attrs") or {}).get("targetId")
                ident = target.strip() if isinstance(target, str) else ""
                number = self.figure_numbers.get(ident)
                paragraph.add_run(
                    f"Figure {number}" if number else _FIGURE_REFERENCE_MISSING
                )
            elif kind == "equationReference":
                target = (node.get("attrs") or {}).get("targetId")
                ident = target.strip() if isinstance(target, str) else ""
                number = self.equation_numbers.get(ident)
                paragraph.add_run(
                    f"Equation ({number})" if number else _EQUATION_REFERENCE_MISSING
                )
            elif kind == "footnote":
                text = (node.get("attrs") or {}).get("text")
                self._add_footnote_reference(
                    paragraph, text if isinstance(text, str) else ""
                )
            else:
                self._add_inline(paragraph, node.get("content"))

    def _add_footnote_reference(self, paragraph: Any, text: str) -> None:
        """Append a native Word footnote reference and remember its text."""
        self.footnotes.append(text)
        number = len(self.footnotes)
        run = paragraph.add_run()
        properties = OxmlElement("w:rPr")
        style = OxmlElement("w:rStyle")
        style.set(qn("w:val"), "FootnoteReference")
        properties.append(style)
        run._r.append(properties)
        reference = OxmlElement("w:footnoteReference")
        reference.set(qn("w:id"), str(number))
        run._r.append(reference)

    # -- blocks ---------------------------------------------------------

    def add_blocks(
        self,
        container: Any,
        nodes: list[dict[str, Any]] | None,
        depth: int = 0,
        quote: bool = False,
    ) -> None:
        for node in nodes or []:
            if isinstance(node, dict):
                self.add_block(container, node, depth, quote)

    def add_block(
        self,
        container: Any,
        node: dict[str, Any],
        depth: int = 0,
        quote: bool = False,
        prefix: str | None = None,
    ) -> None:
        kind = node.get("type")
        if kind == "paragraph":
            self._paragraph(container, node, depth, quote, prefix)
        elif kind == "heading":
            self._heading(container, node, depth)
        elif kind in _LIST_TYPES:
            self._list(container, node, depth, quote)
        elif kind == "blockquote":
            self.add_blocks(container, node.get("content"), depth + 1, True)
        elif kind == "codeBlock":
            self._code_block(container, node)
        elif kind == "horizontalRule":
            self._rule(container)
        elif kind == "figure":
            self._figure(container, node)
        elif kind == "blockMath":
            self._block_math(container, node)
        elif kind == "table":
            self._table(container, node)
        elif kind == "hardBreak":
            return
        else:
            self.add_blocks(container, node.get("content"), depth, quote)

    def _paragraph(
        self,
        container: Any,
        node: dict[str, Any],
        depth: int,
        quote: bool,
        prefix: str | None = None,
    ) -> None:
        paragraph = self._new_paragraph(container, "Quote" if quote else None)
        self._align(paragraph, node.get("attrs") or {})
        if depth or prefix:
            formatter = paragraph.paragraph_format
            formatter.left_indent = Inches(0.3 * depth)
            if prefix:
                formatter.first_line_indent = Inches(-0.3)
                paragraph.add_run(f"{prefix} ")
        self._add_inline(paragraph, node.get("content"))

    def _heading(self, container: Any, node: dict[str, Any], depth: int) -> None:
        level = min(max(_int_attr(node, "level", 1), 1), 6)
        paragraph = self._new_paragraph(container, f"Heading {level}")
        self._align(paragraph, node.get("attrs") or {})
        if depth:
            paragraph.paragraph_format.left_indent = Inches(0.3 * depth)
        self._add_inline(paragraph, node.get("content"))

    def _list(
        self,
        container: Any,
        node: dict[str, Any],
        depth: int,
        quote: bool,
    ) -> None:
        ordered = node.get("type") == "orderedList"
        start = _int_attr(node, "start", 1)
        for index, item in enumerate(node.get("content") or []):
            if not isinstance(item, dict):
                continue
            marker = f"{start + index}." if ordered else "\u2022"
            children = [
                child for child in item.get("content") or [] if isinstance(child, dict)
            ]
            first = True
            for child in children:
                if child.get("type") in _LIST_TYPES:
                    self.add_block(container, child, depth + 1, quote)
                    continue
                self.add_block(
                    container,
                    child,
                    depth + 1,
                    quote,
                    marker if first else None,
                )
                first = False
            if first:
                paragraph = self._new_paragraph(container, "Quote" if quote else None)
                formatter = paragraph.paragraph_format
                formatter.left_indent = Inches(0.3 * (depth + 1))
                formatter.first_line_indent = Inches(-0.3)
                paragraph.add_run(marker)

    def _code_block(self, container: Any, node: dict[str, Any]) -> None:
        text = _inline_text(node.get("content"))
        paragraph = container.add_paragraph()
        self._shade(paragraph, "F5F5F5")
        lines = text.split("\n")
        for index, line in enumerate(lines):
            run = paragraph.add_run(line)
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            if index < len(lines) - 1:
                run.add_break()

    def _rule(self, container: Any) -> None:
        paragraph = container.add_paragraph()
        properties = paragraph._p.get_or_add_pPr()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "auto")
        borders.append(bottom)
        properties.append(borders)

    def _figure(self, container: Any, node: dict[str, Any]) -> None:
        attrs = node.get("attrs") or {}
        raw_caption = str(attrs.get("caption") or attrs.get("alt") or "").strip()
        caption = raw_caption or _FIGURE_FALLBACK
        alt = str(attrs.get("alt") or "")
        numbered = _is_numbered_figure(node)
        number: int | None = None
        if numbered:
            self.figure_number += 1
            number = self.figure_number

        shown = self._add_picture(container, attrs.get("src"), alt)

        if shown:
            if number is not None:
                caption_text = (
                    f"Figure {number}. {raw_caption}"
                    if raw_caption
                    else f"Figure {number}"
                )
            else:
                caption_text = caption
            caption_paragraph = self._new_paragraph(container, "Caption")
            caption_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            caption_paragraph.add_run(caption_text)
        else:
            if number is not None:
                marker_text = (
                    f"[Figure {number}: {raw_caption}]"
                    if raw_caption
                    else f"[Figure {number}]"
                )
            else:
                marker_text = f"[Figure: {caption}]"
            marker = container.add_paragraph()
            marker.alignment = WD_ALIGN_PARAGRAPH.CENTER
            marker.add_run(marker_text)

        note = attrs.get("note")
        if isinstance(note, str):
            lines = [line for line in note.splitlines() if line.strip()]
            if lines:
                note_paragraph = self._new_paragraph(container, None)
                note_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = note_paragraph.add_run("\n".join(lines))
                run.italic = True
                run.font.size = Pt(9)

    def _add_picture(self, container: Any, src: Any, alt: str) -> bool:
        paragraph = container.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        if not self._fill_picture_run(
            run, src, alt, max_width=_MAX_IMAGE_WIDTH
        ):
            paragraph._p.getparent().remove(paragraph._p)
            return False
        return True

    def _add_inline_image(self, paragraph: Any, node: dict[str, Any]) -> None:
        """Embed a small picture inside the running paragraph.

        A missing or unreadable asset becomes a visible marker so the sentence
        never silently loses the picture. The alt text doubles as the Word
        drawing description, exactly like a block figure.
        """
        attrs = node.get("attrs") or {}
        alt = str(attrs.get("alt") or "")
        run = paragraph.add_run()
        if self._fill_picture_run(
            run,
            attrs.get("src"),
            alt,
            max_width=_MAX_INLINE_IMAGE_WIDTH,
            max_height=_MAX_INLINE_IMAGE_HEIGHT,
        ):
            return
        label = alt.strip() or _INLINE_IMAGE_FALLBACK
        paragraph.add_run(f"[Image: {label}]")

    def _fill_picture_run(
        self,
        run: Any,
        src: Any,
        alt: str,
        *,
        max_width: int,
        max_height: int | None = None,
    ) -> bool:
        if not isinstance(src, str):
            return False
        match = _ASSET_SRC.search(src)
        if not match:
            return False
        try:
            path, _mime = pages.get_asset_file(self.project_dir, match.group(1))
        except Exception:
            # A damaged project or missing asset must not abort the export.
            return False
        try:
            data = path.read_bytes()
        except OSError:
            return False

        shape = None
        try:
            # A stream gives the image part a generic name, so the local asset
            # id never appears in the exported package.
            shape = run.add_picture(io.BytesIO(data))
        except Exception:
            # Word cannot read some formats the project accepts (for example
            # WebP). Convert locally through Pillow instead of dropping the
            # figure; the pixels are unchanged.
            try:
                with Image.open(io.BytesIO(data)) as image:
                    buffer = io.BytesIO()
                    image.convert("RGB").save(buffer, format="PNG")
                    buffer.seek(0)
                shape = run.add_picture(buffer)
            except Exception:
                shape = None
        if shape is None:
            return False

        name = alt.strip() or _FIGURE_FALLBACK
        shape._inline.graphic.graphicData.pic.nvPicPr.cNvPr.set("name", name)
        if alt:
            shape._inline.docPr.set("descr", alt)
        width_ratio = (
            max_width / shape.width if shape.width > max_width else 1.0
        )
        height_ratio = (
            max_height / shape.height
            if max_height is not None and shape.height > max_height
            else 1.0
        )
        ratio = min(width_ratio, height_ratio)
        if ratio < 1.0:
            shape.width = int(shape.width * ratio)
            shape.height = int(shape.height * ratio)
        return True

    def _table(self, container: Any, node: dict[str, Any]) -> None:
        rows = [
            row
            for row in node.get("content") or []
            if isinstance(row, dict) and row.get("type") == "tableRow"
        ]
        if not rows:
            return
        column_count = 0
        for row in rows:
            total = 0
            for cell in row.get("content") or []:
                if isinstance(cell, dict):
                    total += _span_attr((cell.get("attrs") or {}).get("colspan"), 1000)
            column_count = max(column_count, total)
        if column_count == 0:
            return

        grid: list[list[tuple[int, int] | None]] = [
            [None] * column_count for _ in rows
        ]
        placements: list[tuple[int, int, int, int, dict[str, Any]]] = []
        for row_index, row in enumerate(rows):
            column = 0
            for cell in row.get("content") or []:
                if not isinstance(cell, dict):
                    continue
                while column < column_count and grid[row_index][column] is not None:
                    column += 1
                if column >= column_count:
                    break
                attrs = cell.get("attrs") or {}
                colspan = _span_attr(attrs.get("colspan"), column_count - column)
                rowspan = _span_attr(attrs.get("rowspan"), len(rows) - row_index)
                while rowspan > 1 and any(
                    grid[row_index + rowspan - 1][offset] is not None
                    for offset in range(column, column + colspan)
                ):
                    rowspan -= 1
                for covered_row in range(row_index, row_index + rowspan):
                    for covered_column in range(column, column + colspan):
                        grid[covered_row][covered_column] = (row_index, column)
                placements.append((row_index, column, rowspan, colspan, cell))
                column += colspan

        table = container.add_table(rows=len(rows), cols=column_count)
        try:
            table.style = "Table Grid"
        except KeyError:
            pass
        for row_index, column, rowspan, colspan, cell in placements:
            target = table.cell(row_index, column)
            if rowspan > 1 or colspan > 1:
                target = target.merge(
                    table.cell(row_index + rowspan - 1, column + colspan - 1)
                )
            self._fill_cell(target, cell)
            if cell.get("type") == "tableHeader":
                self._header_cell(target)

    def _fill_cell(self, target: Any, cell: dict[str, Any]) -> None:
        for block in cell.get("content") or []:
            if isinstance(block, dict):
                self.add_block(target, block)
        paragraphs = target.paragraphs
        if paragraphs and (len(paragraphs) > 1 or target.tables):
            first = paragraphs[0]
            if not first.text and not first.runs:
                first._p.getparent().remove(first._p)

    def _header_cell(self, target: Any) -> None:
        for paragraph in target.paragraphs:
            for run in paragraph.runs:
                run.bold = True
        properties = target._tc.get_or_add_tcPr()
        shade = OxmlElement("w:shd")
        shade.set(qn("w:val"), "clear")
        shade.set(qn("w:color"), "auto")
        shade.set(qn("w:fill"), "F2F2F2")
        properties.append(shade)

    # -- shared formatting ---------------------------------------------

    def _new_paragraph(self, container: Any, style: str | None) -> Any:
        if not style:
            return container.add_paragraph()
        try:
            return container.add_paragraph(style=style)
        except KeyError:
            return container.add_paragraph()

    def _align(self, paragraph: Any, attrs: dict[str, Any]) -> None:
        value = attrs.get("textAlign")
        if isinstance(value, str) and value in _ALIGNMENTS:
            paragraph.alignment = _ALIGNMENTS[value]

    def _shade(self, paragraph: Any, fill: str) -> None:
        properties = paragraph._p.get_or_add_pPr()
        shade = OxmlElement("w:shd")
        shade.set(qn("w:val"), "clear")
        shade.set(qn("w:color"), "auto")
        shade.set(qn("w:fill"), fill)
        properties.append(shade)


def _docx_field(paragraph: Any, instruction: str) -> None:
    """Append a simple Word field (for example a page number) to a paragraph."""
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), f" {instruction} ")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    # Word recalculates the field; this value is only a placeholder for other
    # readers and is never treated as the real page count.
    text.text = "1"
    run.append(text)
    field.append(run)
    paragraph._p.append(field)


def _add_docx_layout_runs(paragraph: Any, text: str, project_name: str) -> None:
    """Write header/footer text, turning page tokens into real Word fields."""
    position = 0
    for match in _LAYOUT_TOKEN_PATTERN.finditer(text):
        if match.start() > position:
            paragraph.add_run(text[position : match.start()])
        token = match.group(1)
        if token == "title":
            paragraph.add_run(project_name)
        elif token == "page":
            _docx_field(paragraph, "PAGE")
        else:
            _docx_field(paragraph, "NUMPAGES")
        position = match.end()
    if position < len(text):
        paragraph.add_run(text[position:])


def _has_layout_page_token(*values: str) -> bool:
    return any(
        token in value for value in values for token in _LAYOUT_PAGE_TOKENS
    )


def _apply_docx_layout(
    document: Any,
    project_name: str,
    header_text: str,
    footer_text: str,
    show_page_numbers: bool,
) -> None:
    """Write the project header/footer into the document's first section.

    A page counter is appended only when the header and footer do not already
    place an explicit ``{page}`` or ``{pages}`` token, so numbers are never
    duplicated.
    """
    section = document.sections[0]
    if header_text:
        _add_docx_layout_runs(section.header.paragraphs[0], header_text, project_name)

    footer = section.footer.paragraphs[0]
    if footer_text:
        _add_docx_layout_runs(footer, footer_text, project_name)

    if show_page_numbers and not _has_layout_page_token(header_text, footer_text):
        if footer_text:
            content_width = (
                section.page_width - section.left_margin - section.right_margin
            )
            footer.paragraph_format.tab_stops.add_tab_stop(
                content_width, WD_TAB_ALIGNMENT.RIGHT
            )
            footer.add_run("\t")
        else:
            footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _docx_field(footer, "PAGE")
        footer.add_run(" / ")
        _docx_field(footer, "NUMPAGES")


def render_docx(
    content: dict[str, Any],
    project_dir: Path,
    project_name: str = "",
    *,
    header_text: str = "",
    footer_text: str = "",
    show_page_numbers: bool = True,
    session: Any = None,
) -> bytes:
    """Render the document as a Word file, embedding local figures and OMML."""
    document = Document()
    properties = document.core_properties
    properties.title = project_name
    # Do not copy the exporting machine's identity into the file.
    properties.author = ""
    properties.last_modified_by = ""
    properties.comments = ""
    _apply_docx_layout(
        document, project_name, header_text, footer_text, show_page_numbers
    )
    renderer = _DocxRenderer(document, project_dir)
    renderer.figure_numbers = _figure_number_map(content)
    renderer.equation_numbers = _equation_number_map(content)
    renderer.add_blocks(document, content.get("content") or [])
    _attach_footnotes(document, renderer.footnotes)
    _embed_docx_fonts(document, content, session)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# --- PDF export ---------------------------------------------------------

# A4 is the common page size for the documents this app rebuilds. The content
# area leaves room on each side for the chosen margin and enough room at the
# bottom for a page number without the text touching it.
_PDF_PAGE_SIZES = {"a4": "a4", "letter": "letter"}
_PDF_MARGINS = {"narrow": 36.0, "normal": 50.0, "wide": 72.0}
_PDF_FONT_ENV = "DOCUREBUILD_PDF_FONT"
_PDF_IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}
)
_TEXT_ALIGNMENTS = frozenset({"left", "center", "right", "justify"})
# An inline picture stays on its sentence's line, so it is much smaller than a
# block figure.
_PDF_INLINE_IMAGE_MAX_WIDTH = 150.0
_PDF_INLINE_IMAGE_MAX_HEIGHT = 90.0
_MYANMAR_TEXT = re.compile(r"[\u1000-\u109F\uA9E0-\uA9FF\uAA60-\uAA7F]")
_MYANMAR_FONT_TOKENS = (
    "myanmar",
    "padauk",
    "mmrtext",
    "myanmarmm",
)


def _pdf_font_dirs() -> list[Path]:
    """Directories that commonly hold system fonts on each platform."""
    directories = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
    ]
    windir = os.environ.get("WINDIR")
    if windir:
        directories.append(Path(windir) / "Fonts")
    # A Windows install can still be reached through a non-Windows shell (for
    # example a mounted drive), so keep the conventional path as a fallback.
    directories.append(Path("C:/Windows/Fonts"))
    return directories


def _myanmar_font_candidates(override: str) -> list[Path]:
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    known = (
        "mmrtext.ttf",
        "NotoSansMyanmar-Regular.ttf",
        "NotoSansMyanmarUI-Regular.ttf",
        "NotoSansMyanmar.ttf",
        "Padauk-Regular.ttf",
        "Padauk.ttf",
    )
    for directory in _pdf_font_dirs():
        for name in known:
            candidates.append(directory / name)
    for directory in _pdf_font_dirs():
        try:
            entries = sorted(directory.rglob("*"))
        except OSError:
            continue
        for entry in entries:
            if entry.suffix.lower() not in {".ttf", ".otf"}:
                continue
            lowered = entry.name.lower()
            if any(token in lowered for token in _MYANMAR_FONT_TOKENS):
                candidates.append(entry)
    return candidates


def _font_has_myanmar(path: Path) -> bool:
    try:
        font = pymupdf.Font(fontfile=str(path))
        return bool(font.has_glyph(ord("မ")))
    except Exception:
        return False


@lru_cache(maxsize=8)
def _find_myanmar_font_cached(override: str) -> Path | None:
    seen: set[str] = set()
    for path in _myanmar_font_candidates(override):
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if not path.is_file() or path.stat().st_size == 0:
                continue
        except OSError:
            continue
        if _font_has_myanmar(path):
            return path
    return None


def _find_myanmar_font() -> Path | None:
    """Find a Unicode Myanmar font, honouring ``DOCUREBUILD_PDF_FONT``."""
    return _find_myanmar_font_cached(os.environ.get(_PDF_FONT_ENV, "").strip())


def _has_myanmar(value: Any) -> bool:
    if isinstance(value, str):
        return _MYANMAR_TEXT.search(value) is not None
    if isinstance(value, dict):
        return any(_has_myanmar(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_myanmar(item) for item in value)
    return False


def _pdf_css(font_file: str | None, extra: str = "") -> str:
    """Styles for the HTML story. Only trusted, generated values are inserted."""
    if font_file:
        face = (
            f"@font-face {{ font-family: docu; src: url({font_file}); }}\n"
            "body { font-family: docu, sans-serif; }"
        )
    else:
        face = "body { font-family: sans-serif; }"
    rules = [
        face,
        extra,
        "body { margin: 0; font-size: 11pt; line-height: 1.45; color: #111; }",
            "h1 { font-size: 21pt; margin: 16pt 0 8pt; }",
            "h2 { font-size: 17pt; margin: 14pt 0 7pt; }",
            "h3 { font-size: 14pt; margin: 12pt 0 6pt; }",
            "h4 { font-size: 12pt; margin: 10pt 0 5pt; }",
            "h5 { font-size: 11pt; margin: 9pt 0 4pt; }",
            "h6 { font-size: 10pt; margin: 8pt 0 4pt; }",
            "p { margin: 0 0 7pt; }",
            (
                "blockquote { margin: 8pt 0 8pt 12pt; padding-left: 9pt; "
                "border-left: 2pt solid #c8c8c8; color: #333; }"
            ),
            "blockquote p { margin: 0 0 4pt; }",
            "ul, ol { margin: 0 0 7pt 18pt; padding: 0; }",
            "li { margin: 0 0 3pt; }",
            "li p { margin: 0; }",
            (
                "pre { font-family: monospace; font-size: 9.5pt; "
                "background-color: #f4f4f4; padding: 6pt; margin: 0 0 7pt; "
                "white-space: pre-wrap; }"
            ),
            "code { font-family: monospace; font-size: 9.5pt; }",
            "a { color: #0b57d0; text-decoration: underline; }",
            "hr { border: none; border-top: 1pt solid #bbb; margin: 10pt 0; }",
            (
                "table { border-collapse: collapse; width: 100%; "
                "margin: 0 0 8pt; }"
            ),
            (
                "th, td { border: 0.6pt solid #999; padding: 3pt 4pt; "
                "vertical-align: top; }"
            ),
            "th { background-color: #f2f2f2; font-weight: bold; }",
            "td p, th p { margin: 0; }",
            "td p + p, th p + p { margin-top: 4pt; }",
            ".figure { text-align: center; margin: 10pt 0; }",
            ".figure p { margin: 0; }",
            ".figure img { max-width: 100%; }",
            ".figure .caption { text-align: center; font-size: 10pt; margin-top: 4pt; }",
            (
                ".figure .note { text-align: center; font-size: 9pt; "
                "font-style: italic; color: #555; margin-top: 2pt; }"
            ),
            ".equation { text-align: center; margin: 8pt 0; }",
            ".equation code { font-size: 10pt; }",
            ".inline-equation { font-size: 9.5pt; }",
            ".inline-image { vertical-align: middle; max-width: 100%; }",
            (
                ".notes-title { font-size: 14pt; margin: 18pt 0 6pt; "
                "border-top: 0.6pt solid #ccc; padding-top: 8pt; }"
            ),
            ".notes { font-size: 9pt; margin-left: 16pt; }",
            ".notes li { margin-bottom: 3pt; }",
        ]
    return "\n".join(rule for rule in rules if rule)


class _PdfFontRegistry:
    """Map document font families to embedded faces for the PDF story.

    MuPDF accepts several ``@font-face`` rules for one family with ``font-weight``
    and ``font-style`` descriptors, so bold and italic runs select the matching
    face instead of a synthesised approximation.
    """

    def __init__(self, archive: Any, families: dict[str, list[Any]]) -> None:
        self._aliases: dict[str, str] = {}
        self._rules: list[str] = []
        index = 0
        for faces in families.values():
            if not faces:
                continue
            index += 1
            token = f"docu-family-{index}"
            embedded = False
            for _tag, italic, weight in _DOCX_FONT_VARIANTS:
                face = _closest_face(faces, italic=italic, weight=weight)
                if face is None or not font_service.embedding_allowed(face):
                    continue
                data = font_service.face_bytes(face)
                if not data:
                    continue
                suffix = ".otf" if data[:4] == b"OTTO" else ".ttf"
                name = f"docu-family-{index}-{abs(weight)}-{'i' if italic else 'r'}{suffix}"
                try:
                    archive.add(data, name)
                except Exception:
                    continue
                descriptor = ""
                if weight >= 600:
                    descriptor += "font-weight: bold;"
                if italic:
                    descriptor += "font-style: italic;"
                self._rules.append(
                    f"@font-face {{ font-family: {token}; src: url({name});"
                    f"{descriptor} }}"
                )
                embedded = True
            if embedded:
                self._aliases[faces[0].family.casefold()] = token
            else:
                # Naming the family still lets a local installation render it;
                # the PDF will fall back to a generic face when it is absent.
                safe = faces[0].family.replace('"', "")
                self._aliases[faces[0].family.casefold()] = f'"{safe}"'

    def css(self) -> str:
        return "\n".join(self._rules)

    def span_style(self, family: str) -> str | None:
        alias = self._aliases.get(family.casefold())
        if alias is None:
            return None
        return f"font-family: {alias}"


class _PdfRenderer:
    """Build escaped HTML for PyMuPDF's story engine."""

    def __init__(
        self,
        content: dict[str, Any],
        project_dir: Path,
        archive: pymupdf.Archive,
        text_width: float,
        max_image_height: float,
        fonts: _PdfFontRegistry | None = None,
    ) -> None:
        self.content = content
        self.project_dir = project_dir
        self.archive = archive
        self.text_width = text_width
        self.max_image_height = max_image_height
        self.fonts = fonts
        self.figure_numbers = _figure_number_map(content)
        self.equation_numbers = _equation_number_map(content)
        self.footnotes: list[str] = []
        self.figure_number = 0
        self.equation_number = 0
        self.image_count = 0
        self._image_cache: dict[
            tuple[str, float | None, float | None], tuple[str, float] | None
        ] = {}

    def render(self) -> str:
        body = self._blocks(self.content.get("content") or [])
        notes = self._notes()
        combined = f"{body}{notes}"
        # Story needs at least one block to create a page.
        return combined or "<p>&nbsp;</p>"

    # -- blocks ---------------------------------------------------------

    def _blocks(self, nodes: list[dict[str, Any]] | None, depth: int = 0) -> str:
        parts: list[str] = []
        for node in nodes or []:
            if isinstance(node, dict):
                rendered = self._block(node, depth)
                if rendered:
                    parts.append(rendered)
        return "".join(parts)

    def _block(self, node: dict[str, Any], depth: int = 0) -> str:
        kind = node.get("type")
        children = node.get("content") or []
        if kind == "paragraph":
            inner = self._inline(children)
            return f"<p{self._align_style(node.get('attrs') or {})}>{inner or '&nbsp;'}</p>"
        if kind == "heading":
            level = min(max(_int_attr(node, "level", 1), 1), 6)
            return (
                f"<h{level}{self._align_style(node.get('attrs') or {})}>"
                f"{self._inline(children)}</h{level}>"
            )
        if kind in _LIST_TYPES:
            return self._list(node, depth)
        if kind == "blockquote":
            return f"<blockquote>{self._blocks(children, depth + 1)}</blockquote>"
        if kind == "codeBlock":
            code = html.escape(_inline_text(children), quote=False)
            return f"<pre>{code}</pre>"
        if kind == "horizontalRule":
            return "<hr>"
        if kind == "figure":
            return self._figure(node)
        if kind == "blockMath":
            return self._block_math(node)
        if kind == "table":
            return self._table(node)
        if kind == "hardBreak":
            return ""
        return self._blocks(children, depth)

    def _list(self, node: dict[str, Any], depth: int) -> str:
        ordered = node.get("type") == "orderedList"
        tag = "ol" if ordered else "ul"
        start = _int_attr(node, "start", 1)
        start_attr = f' start="{start}"' if ordered and start != 1 else ""
        items: list[str] = []
        for item in node.get("content") or []:
            if not isinstance(item, dict):
                continue
            inner = self._blocks(item.get("content") or [], depth + 1)
            items.append(f"<li>{inner or '&nbsp;'}</li>")
        if not items:
            return ""
        return f"<{tag}{start_attr}>{''.join(items)}</{tag}>"

    def _table(self, node: dict[str, Any]) -> str:
        rows = _table_rows(node)
        if not rows:
            return ""
        header = _table_header_row(rows)
        parts = ["<table>"]
        if header:
            parts.append("<thead>")
            parts.append(self._table_row(rows[0]))
            parts.append("</thead><tbody>")
            body_rows = rows[1:]
        else:
            parts.append("<tbody>")
            body_rows = rows
        for row in body_rows:
            parts.append(self._table_row(row))
        parts.append("</tbody></table>")
        return "".join(parts)

    def _table_row(self, row: list[dict[str, Any]]) -> str:
        cells: list[str] = []
        for cell in row:
            tag = "th" if cell.get("type") == "tableHeader" else "td"
            attributes = ""
            colspan = _cell_span(cell, "colspan")
            rowspan = _cell_span(cell, "rowspan")
            if colspan > 1:
                attributes += f' colspan="{colspan}"'
            if rowspan > 1:
                attributes += f' rowspan="{rowspan}"'
            content = self._blocks(cell.get("content") or [])
            cells.append(f"<{tag}{attributes}>{content or '&nbsp;'}</{tag}>")
        return f"<tr>{''.join(cells)}</tr>"

    def _figure(self, node: dict[str, Any]) -> str:
        attrs = node.get("attrs") or {}
        raw_caption = str(attrs.get("caption") or attrs.get("alt") or "").strip()
        caption = raw_caption or _FIGURE_FALLBACK
        numbered = _is_numbered_figure(node)
        number: int | None = None
        if numbered:
            self.figure_number += 1
            number = self.figure_number

        image = self._image(attrs.get("src"))
        parts = ['<div class="figure">']
        if image is not None:
            name, width = image
            alt = str(attrs.get("alt") or "")
            parts.append(
                f'<p><img src="{name}" alt="{html.escape(alt, quote=True)}" '
                f'style="width: {width:.1f}pt"></p>'
            )
            if number is not None:
                text = (
                    f"Figure {number}. {raw_caption}"
                    if raw_caption
                    else f"Figure {number}"
                )
            else:
                text = caption
        else:
            if number is not None:
                text = (
                    f"[Figure {number}: {raw_caption}]"
                    if raw_caption
                    else f"[Figure {number}]"
                )
            else:
                text = f"[Figure: {caption}]"
        parts.append(f'<p class="caption">{html.escape(text, quote=False)}</p>')

        note = attrs.get("note")
        if isinstance(note, str):
            lines = [line for line in note.splitlines() if line.strip()]
            if lines:
                note_text = html.escape("\n".join(lines), quote=False).replace(
                    "\n", "<br>"
                )
                parts.append(f'<p class="note">{note_text}</p>')
        parts.append("</div>")
        return "".join(parts)

    def _block_math(self, node: dict[str, Any]) -> str:
        latex = _equation_latex(node)
        if not latex:
            return ""
        number: int | None = None
        if _is_numbered_equation(node):
            self.equation_number += 1
            number = self.equation_number
        label = f" ({number})" if number is not None else ""
        return (
            f'<div class="equation"><code>{html.escape(latex, quote=False)}</code>'
            f"{label}</div>"
        )

    def _notes(self) -> str:
        if not self.footnotes:
            return ""
        items: list[str] = []
        for text in self.footnotes:
            escaped = html.escape(text, quote=False).replace("\n", "<br>")
            items.append(f"<li>{escaped}</li>")
        return (
            '<h2 class="notes-title">Notes</h2>'
            f'<ol class="notes">{"".join(items)}</ol>'
        )

    # -- inline content -------------------------------------------------

    def _inline(self, nodes: list[dict[str, Any]] | None) -> str:
        parts: list[str] = []
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            kind = node.get("type")
            if kind == "text":
                text = node.get("text")
                if not isinstance(text, str):
                    continue
                escaped = html.escape(text, quote=False).replace("\n", "<br>")
                parts.append(self._marks(escaped, node.get("marks")))
            elif kind == "hardBreak":
                parts.append("<br>")
            elif kind == "inlineMath":
                latex = _equation_latex(node)
                if latex:
                    parts.append(
                        '<code class="inline-equation">'
                        f"{html.escape(latex, quote=False)}</code>"
                    )
            elif kind == "inlineImage":
                attrs = node.get("attrs") or {}
                alt = str(attrs.get("alt") or "")
                image = self._image(
                    attrs.get("src"),
                    max_width=_PDF_INLINE_IMAGE_MAX_WIDTH,
                    max_height=_PDF_INLINE_IMAGE_MAX_HEIGHT,
                )
                if image is None:
                    label = alt.strip() or _INLINE_IMAGE_FALLBACK
                    parts.append(f"[Image: {html.escape(label, quote=False)}]")
                else:
                    name, width = image
                    parts.append(
                        f'<img class="inline-image" src="{name}" '
                        f'alt="{html.escape(alt, quote=True)}" '
                        f'style="width: {width:.1f}pt">'
                    )
            elif kind == "figure":
                attrs = node.get("attrs") or {}
                caption = str(
                    attrs.get("caption") or attrs.get("alt") or _FIGURE_FALLBACK
                ).strip()
                parts.append(
                    f"[Figure: {html.escape(caption, quote=False)}]"
                )
            elif kind == "figureReference":
                target = (node.get("attrs") or {}).get("targetId")
                ident = target.strip() if isinstance(target, str) else ""
                number = self.figure_numbers.get(ident)
                parts.append(
                    f"Figure {number}" if number else _FIGURE_REFERENCE_MISSING
                )
            elif kind == "equationReference":
                target = (node.get("attrs") or {}).get("targetId")
                ident = target.strip() if isinstance(target, str) else ""
                number = self.equation_numbers.get(ident)
                parts.append(
                    f"Equation ({number})"
                    if number
                    else _EQUATION_REFERENCE_MISSING
                )
            elif kind == "footnote":
                text = (node.get("attrs") or {}).get("text")
                self.footnotes.append(text if isinstance(text, str) else "")
                parts.append(
                    f'<sup class="footnote">{len(self.footnotes)}</sup>'
                )
            else:
                parts.append(self._inline(node.get("content")))
        return "".join(parts)

    def _marks(self, text: str, marks: list[dict[str, Any]] | None) -> str:
        kinds = {
            str(mark.get("type")): mark
            for mark in marks or []
            if isinstance(mark, dict)
        }
        rendered = text
        if "code" in kinds:
            rendered = f"<code>{rendered}</code>"
        if "bold" in kinds:
            rendered = f"<strong>{rendered}</strong>"
        if "italic" in kinds:
            rendered = f"<em>{rendered}</em>"
        if "strike" in kinds:
            rendered = f"<s>{rendered}</s>"
        if "underline" in kinds:
            rendered = f"<u>{rendered}</u>"
        if "superscript" in kinds:
            rendered = f"<sup>{rendered}</sup>"
        elif "subscript" in kinds:
            rendered = f"<sub>{rendered}</sub>"
        family = font_service.sanitize_family(
            ((kinds.get("textStyle") or {}).get("attrs") or {}).get("fontFamily")
        )
        if family and self.fonts is not None:
            style = self.fonts.span_style(family)
            if style:
                rendered = f'<span style="{style}">{rendered}</span>'
        href = _safe_link(
            ((kinds.get("link") or {}).get("attrs") or {}).get("href")
        )
        if href:
            rendered = (
                f'<a href="{html.escape(href, quote=True)}">{rendered}</a>'
            )
        return rendered

    # -- assets ---------------------------------------------------------

    def _image(
        self,
        src: Any,
        *,
        max_width: float | None = None,
        max_height: float | None = None,
    ) -> tuple[str, float] | None:
        """Copy one project figure into the story archive.

        Only an asset id from this project's own document can resolve. A
        missing or unreadable image becomes the explicit marker in ``_figure``
        or ``_inline`` instead of aborting the whole export. The optional caps
        keep an inline picture on the same line as its sentence.
        """
        if not isinstance(src, str):
            return None
        match = _ASSET_SRC.search(src)
        if not match:
            return None
        asset_id = match.group(1)
        cache_key = (asset_id, max_width, max_height)
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]
        try:
            path, _mime = pages.get_asset_file(self.project_dir, asset_id)
            data = path.read_bytes()
        except Exception:
            self._image_cache[cache_key] = None
            return None

        suffix = path.suffix.lower()
        try:
            with Image.open(io.BytesIO(data)) as image:
                width_px, height_px = image.size
                if suffix not in _PDF_IMAGE_SUFFIXES:
                    # MuPDF cannot read every format the project accepts
                    # (for example WebP). Convert locally; pixels are unchanged.
                    buffer = io.BytesIO()
                    image.convert("RGB").save(buffer, format="PNG")
                    data = buffer.getvalue()
                    suffix = ".png"
        except Exception:
            self._image_cache[cache_key] = None
            return None

        name = f"figure-{self.image_count}{suffix}"
        self.image_count += 1
        try:
            self.archive.add(data, name)
        except Exception:
            self._image_cache[cache_key] = None
            return None

        width = max(width_px * 72.0 / 96.0, 1.0)
        height = max(height_px * 72.0 / 96.0, 1.0)
        limit_width = min(max_width or self.text_width, self.text_width)
        limit_height = min(max_height or self.max_image_height, self.max_image_height)
        scale = min(
            1.0,
            limit_width / width,
            limit_height / height,
        )
        result = (name, width * scale)
        self._image_cache[cache_key] = result
        return result

    # -- formatting -----------------------------------------------------

    def _align_style(self, attrs: dict[str, Any]) -> str:
        value = attrs.get("textAlign")
        if isinstance(value, str) and value in _TEXT_ALIGNMENTS:
            return f' style="text-align: {value}"'
        return ""


def _layout_text_value(
    text: str, project_name: str, page_number: int, page_total: int
) -> str:
    """Resolve the supported layout tokens for one page."""
    if not text:
        return ""

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "page":
            return str(page_number)
        if token == "pages":
            return str(page_total)
        return project_name

    return _LAYOUT_TOKEN_PATTERN.sub(replace, text)


@lru_cache(maxsize=8)
def _layout_font(font_file: str) -> pymupdf.Font:
    return pymupdf.Font(fontfile=font_file)


def _layout_text_width(text: str, font_file: str | None, fontsize: float) -> float:
    if font_file:
        try:
            return _layout_font(font_file).text_length(text, fontsize)
        except Exception:
            pass
    return pymupdf.get_text_length(text, fontname="helv", fontsize=fontsize)


def _fit_layout_text(
    text: str, max_width: float, font_file: str | None, fontsize: float
) -> str:
    """Keep header/footer text on one line without drawing outside the margin."""
    if max_width <= 0 or not text:
        return ""
    if _layout_text_width(text, font_file, fontsize) <= max_width:
        return text
    tail = "..."
    trimmed = text
    while trimmed and (
        _layout_text_width(trimmed + tail, font_file, fontsize) > max_width
    ):
        trimmed = trimmed[:-1]
    trimmed = trimmed.rstrip()
    return f"{trimmed}{tail}" if trimmed else ""


def _draw_layout_text(
    page: pymupdf.Page,
    text: str,
    rect: pymupdf.Rect,
    *,
    align: int,
    font_file: str | None,
    fontname: str,
    fontsize: float = 8.0,
) -> None:
    """Draw one line of generated chrome (header or footer) inside a margin."""
    value = _fit_layout_text(text, rect.width, font_file, fontsize)
    if not value:
        return
    width = _layout_text_width(value, font_file, fontsize)
    if align == 1:
        x = rect.x0 + max(0.0, (rect.width - width) / 2)
    elif align == 2:
        x = rect.x1 - width
    else:
        x = rect.x0
    page.insert_text(
        pymupdf.Point(x, rect.y1 - fontsize * 0.2),
        value,
        fontsize=fontsize,
        fontname=fontname,
        color=(0.45, 0.45, 0.45),
    )


def render_pdf(
    content: dict[str, Any],
    project_dir: Path,
    project_name: str = "",
    *,
    page_size: str = "a4",
    margin: str = "normal",
    header_text: str = "",
    footer_text: str = "",
    show_page_numbers: bool = True,
    session: Any = None,
) -> bytes:
    """Render the document as an A4 or Letter PDF, fully locally."""
    paper = _PDF_PAGE_SIZES.get(page_size, "a4")
    margin_pt = _PDF_MARGINS.get(margin, _PDF_MARGINS["normal"])
    media_box = pymupdf.paper_rect(paper)
    text_width = media_box.width - 2 * margin_pt
    # Keep a tall scan inside one page while leaving room for its caption.
    max_image_height = max(120.0, media_box.height - 2 * margin_pt - 60.0)

    # Header/footer text participates in the Myanmar font check, so a Burmese
    # running head cannot be written as replacement characters.
    header_source = header_text.replace("{title}", project_name)
    footer_source = footer_text.replace("{title}", project_name)
    has_myanmar = (
        _has_myanmar(content)
        or _has_myanmar(header_source)
        or _has_myanmar(footer_source)
    )
    font_path = _find_myanmar_font() if has_myanmar else None
    if has_myanmar and font_path is None:
        raise AppError(
            422,
            "pdf_font_missing",
            "PDF export needs a Myanmar font on this device. Install Noto Sans "
            "Myanmar or Padauk, or set DOCUREBUILD_PDF_FONT to a font file.",
        )

    archive = pymupdf.Archive()
    font_file: str | None = None
    if font_path is not None:
        suffix = font_path.suffix.lower() or ".ttf"
        font_file = f"docu-font{suffix}"
        try:
            archive.add(str(font_path), font_file)
        except Exception as exc:
            raise AppError(
                422,
                "pdf_font_missing",
                "The Myanmar font could not be loaded for PDF export.",
            ) from exc

    renderer = _PdfRenderer(
        content,
        project_dir,
        archive,
        text_width,
        max_image_height,
        fonts=_PdfFontRegistry(
            archive, font_service.export_faces_for_document(content, session)
        ),
    )
    story = pymupdf.Story(
        html=renderer.render(),
        user_css=_pdf_css(font_file, renderer.fonts.css() if renderer.fonts else ""),
        archive=archive,
    )
    text_rect = media_box + (margin_pt, margin_pt, -margin_pt, -margin_pt)

    def rectfn(_rect_num: int, _filled: pymupdf.Rect) -> tuple[Any, Any, None]:
        return media_box, text_rect, None

    document = story.write_with_links(rectfn)
    total = document.page_count
    layout_font_file = str(font_path) if font_path is not None else None
    layout_fontname = "docu" if font_path is not None else "helv"
    auto_page_numbers = show_page_numbers and not _has_layout_page_token(
        header_text, footer_text
    )
    for index, page in enumerate(document, start=1):
        header_value = _layout_text_value(header_text, project_name, index, total)
        footer_value = _layout_text_value(footer_text, project_name, index, total)
        if font_path is not None and (header_value or footer_value):
            page.insert_font(fontname=layout_fontname, fontfile=layout_font_file)

        if header_value:
            header_rect = pymupdf.Rect(
                margin_pt,
                max(2.0, margin_pt - 24.0),
                page.rect.width - margin_pt,
                margin_pt - 2.0,
            )
            _draw_layout_text(
                page,
                header_value,
                header_rect,
                align=0,
                font_file=layout_font_file,
                fontname=layout_fontname,
            )

        if footer_value or auto_page_numbers:
            footer_rect = pymupdf.Rect(
                margin_pt,
                page.rect.height - margin_pt + 2,
                page.rect.width - margin_pt,
                page.rect.height - margin_pt + 20,
            )
            if footer_value:
                # Leave the right end of the margin for an automatic counter.
                text_rect = (
                    pymupdf.Rect(
                        footer_rect.x0,
                        footer_rect.y0,
                        footer_rect.x1 - 80.0,
                        footer_rect.y1,
                    )
                    if auto_page_numbers
                    else footer_rect
                )
                _draw_layout_text(
                    page,
                    footer_value,
                    text_rect,
                    align=0,
                    font_file=layout_font_file,
                    fontname=layout_fontname,
                )
            if auto_page_numbers:
                page.insert_textbox(
                    footer_rect,
                    f"{index} / {total}",
                    fontsize=8,
                    fontname="helv",
                    align=2 if footer_value else 1,
                    color=(0.45, 0.45, 0.45),
                )

    document.set_metadata(
        {
            "title": project_name,
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "DocuRebuild",
            "producer": "DocuRebuild",
            "creationDate": "",
            "modDate": "",
        }
    )
    return document.tobytes(
        garbage=4,
        deflate=True,
        no_new_id=True,
        reproducible=True,
    )


def export_document(
    project_dir: Path,
    project_name: str,
    fmt: ExportFormat,
    *,
    pdf_page_size: str = "a4",
    pdf_margin: str = "normal",
    layout: dict[str, Any] | None = None,
    session: Any = None,
) -> tuple[bytes, str, str]:
    """Return ``(body, filename, content_type)`` for the stored document.

    ``layout`` carries the project's page header/footer. It is used by Word and
    PDF; Markdown and plain text are not paginated, so they ignore it.
    """
    document = documents.read_document(project_dir)
    layout = layout or {}
    header_text = str(layout.get("header_text") or "")
    footer_text = str(layout.get("footer_text") or "")
    show_page_numbers = bool(layout.get("show_page_numbers", True))
    if fmt == "docx":
        body = render_docx(
            document["content"],
            project_dir,
            project_name,
            header_text=header_text,
            footer_text=footer_text,
            show_page_numbers=show_page_numbers,
            session=session,
        )
    elif fmt == "pdf":
        body = render_pdf(
            document["content"],
            project_dir,
            project_name,
            page_size=pdf_page_size,
            margin=pdf_margin,
            header_text=header_text,
            footer_text=footer_text,
            show_page_numbers=show_page_numbers,
            session=session,
        )
    else:
        body = render(document["content"], fmt).encode("utf-8")
    return body, download_filename(project_name, fmt), CONTENT_TYPES[fmt]
