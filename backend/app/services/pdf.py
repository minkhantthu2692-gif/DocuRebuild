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
        try:
            raw_words = page.get_text("words")
        except Exception:
            raw_words = []
        page_height = float(page.rect.height) * scale
    except Exception:
        return "", []

    prepared: list[dict[str, Any]] = []
    line_heights: list[float] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        line_spans: list[list[tuple[float, float]]] = []
        max_height = 0.0
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text")]
            text = "".join(str(span["text"]) for span in spans).strip()
            if not text:
                continue
            lines.append(text)
            line_spans.append(
                sorted(
                    (float(span["bbox"][0]), float(span["bbox"][2]))
                    for span in spans
                    if len(span.get("bbox", ())) >= 4
                )
            )
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
                "bbox": (x0, y0, x1, y1),
                "line_spans": line_spans,
                "words": [],
            }
        )

    if not prepared:
        return "", []

    # ``words`` carries exact word boxes, which a table proposal can use. Each
    # word is attached to the text block that contains its centre. Nothing is
    # estimated from character widths, so a proposal never invents geometry.
    for raw_word in raw_words:
        if len(raw_word) < 8:
            continue
        word_text = str(raw_word[4]).strip()
        if not word_text:
            continue
        wx0, wy0, wx1, wy1 = (float(value) for value in raw_word[:4])
        center_x = (wx0 + wx1) / 2
        center_y = (wy0 + wy1) / 2
        owner = None
        for item in prepared:
            bx0, by0, bx1, by1 = item["bbox"]
            if bx0 - 1 <= center_x <= bx1 + 1 and by0 - 1 <= center_y <= by1 + 1:
                owner = item
                break
        if owner is None:
            continue
        owner["words"].append(
            {
                "text": word_text,
                "confidence": None,
                "x": round(wx0 * scale),
                "y": round(wy0 * scale),
                "width": max(round((wx1 - wx0) * scale), 1),
                "height": max(round((wy1 - wy0) * scale), 1),
                "line": int(raw_word[6]),
            }
        )

    for item in prepared:
        item["words"].sort(key=lambda word: (word["line"], word["x"]))

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
                    y=item["y"],
                    height=item["height"],
                    page_height=page_height,
                    line_spans=item["line_spans"],
                ),
                "text": item["text"],
                "confidence": None,
                "x": item["x"],
                "y": item["y"],
                "width": item["width"],
                "height": item["height"],
                "line_count": item["line_count"],
                "word_count": item["word_count"],
                "words": item["words"],
            }
        )
    text = "\n\n".join(block["text"] for block in blocks)
    return text, blocks


def engine_version() -> str | None:
    if pymupdf is None:
        return None
    return getattr(pymupdf, "__version__", None) or getattr(pymupdf, "VersionBind", None)
