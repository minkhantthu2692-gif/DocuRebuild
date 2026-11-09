from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.errors import AppError
from app.services.layout import classify_text_block

try:  # PyMuPDF is a free, local dependency but stays optional at runtime.
    import pymupdf
except ImportError:  # pragma: no cover - exercised only on incomplete installs
    pymupdf = None  # type: ignore[assignment]


def pdf_available() -> bool:
    return pymupdf is not None


def _require_support():
    if pymupdf is None:
        raise AppError(
            409,
            "pdf_unavailable",
            "PDF support is not installed on this device.",
        )
    return pymupdf


def open_document(path: Path):
    """Open and validate a PDF, converting library errors to typed app errors."""
    module = _require_support()
    try:
        document = module.open(path)
    except Exception as exc:
        raise AppError(422, "pdf_unreadable", "The PDF file could not be read.") from exc
    if document.needs_pass:
        document.close()
        raise AppError(
            422,
            "pdf_encrypted",
            "Password-protected PDFs are not supported. Remove the password first.",
        )
    if document.page_count == 0:
        document.close()
        raise AppError(422, "pdf_empty", "The PDF does not contain any pages.")
    return document


def validate_document(path: Path, max_pages: int) -> int:
    document = open_document(path)
    try:
        if document.page_count > max_pages:
            raise AppError(
                422,
                "pdf_too_many_pages",
                f"The PDF has {document.page_count} pages; the limit is {max_pages}.",
            )
        return int(document.page_count)
    finally:
        document.close()


def render_page(document, index: int, dpi: int) -> Image.Image:
    module = _require_support()
    try:
        page = document.load_page(index)
        matrix = module.Matrix(dpi / 72.0, dpi / 72.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    except Exception as exc:
        raise AppError(
            422,
            "pdf_page_render_failed",
            f"PDF page {index + 1} could not be rendered.",
        ) from exc


def extract_text(
    document, index: int, scale: float
) -> tuple[str, list[dict[str, Any]]]:
    """Extract the embedded text layer in reading order.

    Coordinates are converted from PDF points to rendered-page pixels so blocks
    line up with the image shown in the workspace. Embedded text has no OCR
    confidence score, so ``confidence`` stays ``None`` rather than pretending to
    be certain.
    """
    try:
        page = document.load_page(index)
        data = page.get_text("dict", sort=True)
    except Exception:
        return "", []

    prepared: list[dict[str, Any]] = []
    line_heights: list[float] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        max_height = 0.0
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text")]
            text = "".join(str(span["text"]) for span in spans).strip()
            if not text:
                continue
            lines.append(text)
            size = max((float(span.get("size", 0) or 0) for span in spans), default=0.0)
            max_height = max(max_height, size)
        text = "\n".join(lines).strip()
        if not text:
            continue
        x0, y0, x1, y1 = (float(value) for value in block.get("bbox", (0, 0, 0, 0)))
        height = max(y1 - y0, max_height * 1.2, 1.0)
        width = max(x1 - x0, 1.0)
        line_heights.append(height)
        prepared.append(
            {
                "text": text,
                "x": round(x0 * scale),
                "y": round(y0 * scale),
                "width": round(width * scale),
                "height": round(height * scale),
                "line_count": len(lines),
                "word_count": sum(len(line.split()) for line in lines),
                "max_line_height": height,
            }
        )

    if not prepared:
        return "", []

    median_height = statistics.median(line_heights) if line_heights else 1.0
    blocks: list[dict[str, Any]] = []
    for block_number, item in enumerate(prepared, start=1):
        blocks.append(
            {
                "block_index": block_number,
                "kind": classify_text_block(
                    item["text"],
                    item["max_line_height"],
                    median_height,
                    item["word_count"],
                ),
                "text": item["text"],
                "confidence": None,
                "x": item["x"],
                "y": item["y"],
                "width": item["width"],
                "height": item["height"],
                "line_count": item["line_count"],
                "word_count": item["word_count"],
            }
        )
    text = "\n\n".join(block["text"] for block in blocks)
    return text, blocks


def engine_version() -> str | None:
    if pymupdf is None:
        return None
    return getattr(pymupdf, "__version__", None) or getattr(pymupdf, "VersionBind", None)
