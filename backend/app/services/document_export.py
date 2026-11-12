"""Deterministic TXT and Markdown export for the Tiptap document.

The document is stored as Tiptap JSON. This module renders that JSON without
any external dependency, so export works fully offline. It is intentionally
lossless-first: every text node is preserved and only the presentation is
converted. Content that cannot be represented exactly (for example an
extracted figure stored as a local asset) is written as an explicit marker
instead of being dropped silently.

Markdown output is escaped so extracted text can never become markup: a
heading-like line inside a paragraph stays literal text, and raw HTML is
neutralised. Figure image sources are never included because they are local
API paths that are meaningless outside the app.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Literal

from app.services import documents

ExportFormat = Literal["markdown", "txt"]

CONTENT_TYPES: dict[ExportFormat, str] = {
    "markdown": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}
EXTENSIONS: dict[ExportFormat, str] = {"markdown": "md", "txt": "txt"}

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
    caption = attrs.get("caption") or attrs.get("alt") or _FIGURE_FALLBACK
    caption = str(caption).strip() or _FIGURE_FALLBACK
    if markdown:
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


def _equation_marker(node: dict[str, Any], *, markdown: bool, block: bool) -> str:
    latex = _equation_latex(node)
    if not latex:
        return ""
    if not markdown:
        # Plain text keeps the exact LaTeX source the user typed.
        return latex
    # Math must never be escaped as prose, or its backslashes break.
    return f"$$\n{latex}\n$$" if block else f"${latex}$"


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
    body = _blocks_markdown(content.get("content") or [])
    return f"{body}\n" if body else ""


def render_text(content: dict[str, Any]) -> str:
    """Render a Tiptap document as plain text, ending with a single newline."""
    body = _blocks_text(content.get("content") or [])
    return f"{body}\n" if body else ""


def render(content: dict[str, Any], fmt: ExportFormat) -> str:
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


def export_document(
    project_dir: Path, project_name: str, fmt: ExportFormat
) -> tuple[str, str, str]:
    """Return ``(body, filename, content_type)`` for the stored document."""
    document = documents.read_document(project_dir)
    body = render(document["content"], fmt)
    return body, download_filename(project_name, fmt), CONTENT_TYPES[fmt]
