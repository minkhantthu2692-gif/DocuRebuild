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
