"""Deterministic TXT, Markdown and Word export for the Tiptap document.

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
"""

from __future__ import annotations

import html
import io
import re
from pathlib import Path
from typing import Any, Literal

import latex2mathml.converter
import mathml2omml
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt
from PIL import Image

from app.services import documents, pages

ExportFormat = Literal["markdown", "txt", "docx"]
TextExportFormat = Literal["markdown", "txt"]

CONTENT_TYPES: dict[ExportFormat, str] = {
    "markdown": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}
EXTENSIONS: dict[ExportFormat, str] = {
    "markdown": "md",
    "txt": "txt",
    "docx": "docx",
}

_MARKDOWN_SPECIALS = frozenset("\\`*_[]<>")
_SAFE_LINK_PATTERN = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_FIGURE_FALLBACK = "Figure"


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
    body = _apply_figure_numbers(
        _apply_equation_numbers(_blocks_markdown(content.get("content") or []))
    )
    return f"{body}\n" if body else ""


def render_text(content: dict[str, Any]) -> str:
    """Render a Tiptap document as plain text, ending with a single newline."""
    body = _apply_figure_numbers(
        _apply_equation_numbers(_blocks_text(content.get("content") or []))
    )
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


class _DocxRenderer:
    """Turn the stored Tiptap JSON into native Word content."""

    def __init__(self, document: Any, project_dir: Path) -> None:
        self.document = document
        self.project_dir = project_dir
        self.equation_number = 0
        self.figure_number = 0
        self._omml_cache: dict[str, str | None] = {}

    # -- equations -----------------------------------------------------

    def _omml(self, latex: str) -> str | None:
        if latex in self._omml_cache:
            return self._omml_cache[latex]
        source: str | None
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

    def _add_hyperlink(
        self, paragraph: Any, text: str, url: str, marks: dict[str, Any]
    ) -> None:
        relationship_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), relationship_id)
        run = OxmlElement("w:r")
        properties = OxmlElement("w:rPr")
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
            elif kind == "hardBreak":
                paragraph.add_run().add_break()
            elif kind == "figure":
                # A figure inside a sentence has no place in Word's flow; keep
                # its caption so no information disappears.
                attrs = node.get("attrs") or {}
                caption = attrs.get("caption") or attrs.get("alt") or _FIGURE_FALLBACK
                paragraph.add_run(f"[Figure: {caption}]")
            else:
                self._add_inline(paragraph, node.get("content"))

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

        paragraph = container.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
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
            paragraph._p.getparent().remove(paragraph._p)
            return False

        name = alt.strip() or "Figure"
        shape._inline.graphic.graphicData.pic.nvPicPr.cNvPr.set("name", name)
        if alt:
            shape._inline.docPr.set("descr", alt)
        if shape.width > _MAX_IMAGE_WIDTH:
            ratio = _MAX_IMAGE_WIDTH / shape.width
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


def render_docx(
    content: dict[str, Any], project_dir: Path, project_name: str = ""
) -> bytes:
    """Render the document as a Word file, embedding local figures and OMML."""
    document = Document()
    properties = document.core_properties
    properties.title = project_name
    # Do not copy the exporting machine's identity into the file.
    properties.author = ""
    properties.last_modified_by = ""
    properties.comments = ""
    renderer = _DocxRenderer(document, project_dir)
    renderer.add_blocks(document, content.get("content") or [])
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def export_document(
    project_dir: Path, project_name: str, fmt: ExportFormat
) -> tuple[bytes, str, str]:
    """Return ``(body, filename, content_type)`` for the stored document."""
    document = documents.read_document(project_dir)
    if fmt == "docx":
        body = render_docx(document["content"], project_dir, project_name)
    else:
        body = render(document["content"], fmt).encode("utf-8")
    return body, download_filename(project_name, fmt), CONTENT_TYPES[fmt]
