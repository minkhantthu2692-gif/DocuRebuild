from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import resolve_within
from app.db.project_schema import project_db, utc_iso
from app.services import image_edits as edits_service
from app.services import pdf as pdf_service

logger = logging.getLogger(__name__)

THUMBNAIL_EDGE = 480
PDF_EXTENSION = ".pdf"
PDF_TEXT_ENGINE = "pdf-text"


class ImportCancelled(Exception):
    """Raised when a cooperative import cancellation is observed.

    The exception deliberately carries no partial result. Callers inspect the
    job row or the pages that were already committed to report progress.
    """


@dataclass(frozen=True)
class ImportProgress:
    imported_pages: int
    total_pages: int
    current_file: str | None


ProgressCallback = Callable[[ImportProgress], None]

# Formats the browser can display directly.
BROWSER_SAFE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Formats that are accepted but need a display copy.
CONVERTED_EXTENSIONS = {".bmp", ".tif", ".tiff"}

MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

SUPPORTED_EXTENSIONS = set(MIME_BY_EXTENSION)
SUPPORTED_IMPORT_EXTENSIONS = SUPPORTED_EXTENSIONS | {PDF_EXTENSION}

Image.MAX_IMAGE_PIXELS = 180_000_000


def _now() -> str:
    return utc_iso()


def _page_payload(row) -> dict[str, Any]:
    """Serialise a page row, decoding the stored edit document."""
    payload = dict(row)
    payload["edits"] = edits_service.decode_edits(payload.get("edits"))
    return payload


def normalise_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_image_name(filename: str) -> str:
    extension = normalise_extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError(
            400,
            "unsupported_file_type",
            f"Unsupported file type for '{filename}'. Use JPG, PNG, WEBP, BMP or TIFF.",
        )
    return extension


def validate_import_name(filename: str) -> str:
    extension = normalise_extension(filename)
    if extension not in SUPPORTED_IMPORT_EXTENSIONS:
        raise AppError(
            400,
            "unsupported_file_type",
            f"Unsupported file type for '{filename}'. Use JPG, PNG, WEBP, BMP, TIFF or PDF.",
        )
    if extension == PDF_EXTENSION and not pdf_service.pdf_available():
        raise AppError(
            409,
            "pdf_unavailable",
            "PDF support is not installed on this device.",
        )
    return extension


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_image(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            source.load()
            transposed = ImageOps.exif_transpose(source)
            image = transposed.copy()
        return image
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise AppError(422, "image_unreadable", "The image file could not be read.") from exc


def _flatten_for_web(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA"):
        return image.convert("RGBA")
    if image.mode not in ("RGB", "L"):
        return image.convert("RGB")
    return image


def _write_thumbnail(image: Image.Image, target: Path) -> tuple[int, int, int]:
    thumb = _flatten_for_web(image.copy())
    thumb.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE), Image.Resampling.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(target, format="WEBP", quality=84, method=4)
    return thumb.width, thumb.height, target.stat().st_size


def _insert_asset(
    conn,
    *,
    asset_id: str,
    kind: str,
    relative_path: str,
    mime_type: str,
    byte_size: int,
    checksum: str | None,
    width: int | None,
    height: int | None,
) -> None:
    conn.execute(
        """
        INSERT INTO assets (id, kind, relative_path, mime_type, byte_size, checksum,
                            width, height, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            kind,
            relative_path,
            mime_type,
            byte_size,
            checksum,
            width,
            height,
            _now(),
        ),
    )


def _import_image(
    conn,
    project_dir: Path,
    *,
    filename: str,
    temp_path: Path,
    extension: str,
    width: int,
    height: int,
    page_number: int,
    created_files: list[Path],
    created_assets: list[str] | None = None,
) -> dict[str, Any]:
    page_id = str(uuid.uuid4())
    original_id = str(uuid.uuid4())
    thumbnail_id = str(uuid.uuid4())
    relative_source = f"source/{original_id}{extension}"
    source_path = project_dir / relative_source
    source_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(temp_path), str(source_path))
    created_files.append(source_path)

    image = _load_image(source_path)
    display_id: str | None = None
    display_width, display_height = image.width, image.height

    if extension in CONVERTED_EXTENSIONS:
        display_id = str(uuid.uuid4())
        relative_display = f"processed/{page_id}-display.png"
        display_path = project_dir / relative_display
        display_path.parent.mkdir(parents=True, exist_ok=True)
        _flatten_for_web(image).save(display_path, format="PNG", optimize=False)
        created_files.append(display_path)
        _insert_asset(
            conn,
            asset_id=display_id,
            kind="processed",
            relative_path=relative_display,
            mime_type="image/png",
            byte_size=display_path.stat().st_size,
            checksum=None,
            width=display_width,
            height=display_height,
        )
        if created_assets is not None:
            created_assets.append(display_id)

    thumbnail_relative = f"thumbnails/{page_id}.webp"
    thumbnail_path = project_dir / thumbnail_relative
    thumb_width, thumb_height, thumb_size = _write_thumbnail(image, thumbnail_path)
    created_files.append(thumbnail_path)
    image.close()

    _insert_asset(
        conn,
        asset_id=original_id,
        kind="original",
        relative_path=relative_source,
        mime_type=MIME_BY_EXTENSION[extension],
        byte_size=source_path.stat().st_size,
        checksum=_sha256(source_path),
        width=width,
        height=height,
    )
    _insert_asset(
        conn,
        asset_id=thumbnail_id,
        kind="thumbnail",
        relative_path=thumbnail_relative,
        mime_type="image/webp",
        byte_size=thumb_size,
        checksum=None,
        width=thumb_width,
        height=thumb_height,
    )
    if created_assets is not None:
        created_assets.extend([original_id, thumbnail_id])

    now = _now()
    conn.execute(
        """
        INSERT INTO pages (id, page_number, source_kind, status, width, height,
                           original_asset_id, display_asset_id, thumbnail_asset_id,
                           original_filename, rotation, created_at, updated_at)
        VALUES (?, ?, 'image', 'ready', ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            page_id,
            page_number,
            display_width,
            display_height,
            original_id,
            display_id,
            thumbnail_id,
            filename,
            now,
            now,
        ),
    )
    return _page_payload(
        conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    )


def _insert_embedded_text_run(
    conn, page_id: str, display_asset_id: str, text: str, blocks: list[dict]
) -> None:
    if not text.strip() or not blocks:
        return
    run_id = str(uuid.uuid4())
    now = _now()
    conn.execute(
        """
        INSERT INTO ocr_runs (id, page_id, status, engine, engine_version, languages,
                              source_asset_id, rotation, mean_confidence, text,
                              created_at, updated_at, completed_at)
        VALUES (?, ?, 'succeeded', ?, ?, '', ?, 0, NULL, ?, ?, ?, ?)
        """,
        (
            run_id,
            page_id,
            PDF_TEXT_ENGINE,
            pdf_service.engine_version(),
            display_asset_id,
            text,
            now,
            now,
            now,
        ),
    )
    for block in blocks:
        conn.execute(
            """
            INSERT INTO ocr_blocks (id, run_id, page_id, block_index, kind, text,
                                    confidence, x, y, width, height, line_count,
                                    word_count, verified, corrected, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                run_id,
                page_id,
                block["block_index"],
                block["kind"],
                block["text"],
                block["x"],
                block["y"],
                block["width"],
                block["height"],
                block["line_count"],
                block["word_count"],
                now,
                now,
            ),
        )


def _import_pdf_file(
    project_dir: Path,
    *,
    filename: str,
    temp_path: Path,
    page_count: int,
    next_number: int,
    created_files: list[Path],
    created_assets: list[str],
    cancel: threading.Event | None = None,
    on_page: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Import one PDF, committing each rendered page separately.

    Committing per page keeps progress observable and limits how much work a
    cancellation has to roll back. The immutable PDF is stored once and shared
    by every page it produces.
    """
    settings = get_settings()
    pdf_asset_id = str(uuid.uuid4())
    relative_source = f"source/{pdf_asset_id}.pdf"
    source_path = project_dir / relative_source
    source_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(temp_path), str(source_path))
    created_files.append(source_path)
    created_assets.append(pdf_asset_id)

    with project_db(project_dir) as conn:
        _insert_asset(
            conn,
            asset_id=pdf_asset_id,
            kind="original",
            relative_path=relative_source,
            mime_type="application/pdf",
            byte_size=source_path.stat().st_size,
            checksum=_sha256(source_path),
            width=None,
            height=None,
        )

    document = pdf_service.open_document(source_path)
    rows: list[dict[str, Any]] = []
    try:
        scale = settings.pdf_render_dpi / 72.0
        for index in range(page_count):
            if cancel is not None and cancel.is_set():
                raise ImportCancelled()

            page_id = str(uuid.uuid4())
            display_id = str(uuid.uuid4())
            thumbnail_id = str(uuid.uuid4())

            image = pdf_service.render_page(document, index, settings.pdf_render_dpi)
            relative_display = f"processed/{page_id}-page.png"
            display_path = project_dir / relative_display
            display_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(display_path, format="PNG", optimize=False)
            created_files.append(display_path)
            width, height = image.width, image.height

            thumbnail_relative = f"thumbnails/{page_id}.webp"
            thumbnail_path = project_dir / thumbnail_relative
            thumb_width, thumb_height, thumb_size = _write_thumbnail(image, thumbnail_path)
            created_files.append(thumbnail_path)
            image.close()

            with project_db(project_dir) as conn:
                _insert_asset(
                    conn,
                    asset_id=display_id,
                    kind="processed",
                    relative_path=relative_display,
                    mime_type="image/png",
                    byte_size=display_path.stat().st_size,
                    checksum=None,
                    width=width,
                    height=height,
                )
                _insert_asset(
                    conn,
                    asset_id=thumbnail_id,
                    kind="thumbnail",
                    relative_path=thumbnail_relative,
                    mime_type="image/webp",
                    byte_size=thumb_size,
                    checksum=None,
                    width=thumb_width,
                    height=thumb_height,
                )

                now = _now()
                conn.execute(
                    """
                    INSERT INTO pages (id, page_number, source_kind, status, width, height,
                                       original_asset_id, display_asset_id, thumbnail_asset_id,
                                       original_filename, rotation, pdf_page_number,
                                       created_at, updated_at)
                    VALUES (?, ?, 'pdf', 'ready', ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        page_id,
                        next_number + index,
                        width,
                        height,
                        pdf_asset_id,
                        display_id,
                        thumbnail_id,
                        filename,
                        index + 1,
                        now,
                        now,
                    ),
                )

                text, blocks = pdf_service.extract_text(document, index, scale)
                _insert_embedded_text_run(conn, page_id, display_id, text, blocks)
                row = _page_payload(
                    conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
                )

            created_assets.extend([display_id, thumbnail_id])
            rows.append(row)
            if on_page is not None:
                on_page(row)
    finally:
        document.close()
    return rows


def _import_image_file(
    project_dir: Path,
    *,
    filename: str,
    temp_path: Path,
    extension: str,
    width: int,
    height: int,
    page_number: int,
    created_files: list[Path],
    created_assets: list[str],
) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        return _import_image(
            conn,
            project_dir,
            filename=filename,
            temp_path=temp_path,
            extension=extension,
            width=width,
            height=height,
            page_number=page_number,
            created_files=created_files,
            created_assets=created_assets,
        )


def inspect_uploads(uploads: list[tuple[str, Path]]) -> list[dict[str, Any]]:
    """Validate uploads without mutating the project.

    Every file is checked before the import starts so a bad file cannot leave a
    half-imported batch. PDF page counts feed progress reporting.
    """
    if not uploads:
        raise AppError(400, "no_files", "No files were provided.")

    settings = get_settings()
    inspected: list[dict[str, Any]] = []
    for filename, temp_path in uploads:
        extension = validate_import_name(filename)
        if extension == PDF_EXTENSION:
            page_count = pdf_service.validate_document(temp_path, settings.pdf_max_pages)
            inspected.append(
                {
                    "filename": filename,
                    "temp_path": temp_path,
                    "extension": extension,
                    "page_count": page_count,
                }
            )
        else:
            try:
                image = _load_image(temp_path)
            except AppError:
                raise AppError(422, "image_unreadable", f"'{filename}' is not a readable image.")
            inspected.append(
                {
                    "filename": filename,
                    "temp_path": temp_path,
                    "extension": extension,
                    "width": image.width,
                    "height": image.height,
                }
            )
            image.close()
    return inspected


def _next_page_number(project_dir: Path) -> int:
    with project_db(project_dir) as conn:
        return int(
            conn.execute(
                "SELECT COALESCE(MAX(page_number), 0) + 1 AS next FROM pages"
            ).fetchone()["next"]
        )


def discard_temporary_uploads(uploads: list[tuple[str, Path]]) -> None:
    for _filename, temp_path in uploads:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best effort cleanup.
            logger.warning("Could not remove temporary upload %s", temp_path)


def _cleanup_import(
    project_dir: Path,
    page_ids: list[str],
    asset_ids: list[str],
    files: list[Path],
) -> None:
    """Remove pages, assets and files created by a failed or cancelled import."""
    if page_ids or asset_ids:
        try:
            with project_db(project_dir) as conn:
                for page_id in page_ids:
                    conn.execute("DELETE FROM ocr_blocks WHERE page_id = ?", (page_id,))
                    conn.execute("DELETE FROM ocr_runs WHERE page_id = ?", (page_id,))
                    conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))
                for asset_id in asset_ids:
                    conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
                _renumber(conn)
        except Exception:  # pragma: no cover - project may have been removed.
            logger.exception("Could not roll back an interrupted import")

    for path in files:
        try:
            path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best effort cleanup.
            logger.warning("Could not remove imported file %s", path)


def _add_import_history(project_dir: Path, count: int, *, cancelled: bool = False) -> None:
    if cancelled:
        event_type = "pages_import_cancelled"
        summary = f"Imported {count} page(s) before the import was cancelled"
    else:
        event_type = "pages_imported"
        summary = f"Imported {count} page(s)"
    with project_db(project_dir) as conn:
        conn.execute(
            "INSERT INTO history_events (id, event_type, summary, payload, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                event_type,
                summary,
                json.dumps({"count": count, "cancelled": cancelled}, ensure_ascii=False),
                _now(),
            ),
        )


def import_uploads(
    project_dir: Path,
    uploads: list[tuple[str, Path]],
    *,
    inspected: list[dict[str, Any]] | None = None,
    cancel: threading.Event | None = None,
    on_progress: ProgressCallback | None = None,
    keep_completed_on_failure: bool = False,
) -> list[dict[str, Any]]:
    """Import validated temporary image or PDF files as immutable source pages.

    Originals are stored once under ``source/`` and never modified again. Work is
    committed per file (and per PDF page) so progress survives a long batch and a
    cancellation only has to undo the file currently being processed.

    ``keep_completed_on_failure`` keeps pages from files that finished before an
    error or cancellation. The synchronous compatibility wrapper leaves it off
    to preserve all-or-nothing behaviour for simple clients.
    """
    if not uploads:
        raise AppError(400, "no_files", "No files were provided.")

    items = inspected if inspected is not None else inspect_uploads(uploads)
    total_pages = sum(int(item.get("page_count", 1)) for item in items)
    next_number = _next_page_number(project_dir)

    imported: list[dict[str, Any]] = []
    completed_pages: list[str] = []
    completed_assets: list[str] = []
    completed_files: list[Path] = []
    file_pages: list[str] = []
    file_assets: list[str] = []
    file_files: list[Path] = []

    def report(filename: str | None) -> None:
        if on_progress is not None:
            on_progress(ImportProgress(len(imported), total_pages, filename))

    try:
        for item in items:
            if cancel is not None and cancel.is_set():
                raise ImportCancelled()

            file_pages, file_assets, file_files = [], [], []
            filename = item["filename"]
            report(filename)

            if item["extension"] == PDF_EXTENSION:

                def handle_page(row: dict[str, Any]) -> None:
                    imported.append(row)
                    file_pages.append(row["id"])
                    report(filename)

                rows = _import_pdf_file(
                    project_dir,
                    filename=filename,
                    temp_path=item["temp_path"],
                    page_count=int(item["page_count"]),
                    next_number=next_number,
                    created_files=file_files,
                    created_assets=file_assets,
                    cancel=cancel,
                    on_page=handle_page,
                )
            else:
                row = _import_image_file(
                    project_dir,
                    filename=filename,
                    temp_path=item["temp_path"],
                    extension=item["extension"],
                    width=int(item["width"]),
                    height=int(item["height"]),
                    page_number=next_number,
                    created_files=file_files,
                    created_assets=file_assets,
                )
                imported.append(row)
                file_pages.append(row["id"])
                rows = [row]
                report(filename)

            next_number += len(rows)
            completed_pages.extend(file_pages)
            completed_assets.extend(file_assets)
            completed_files.extend(file_files)
            file_pages, file_assets, file_files = [], [], []

        _add_import_history(project_dir, len(imported))
        return imported
    except ImportCancelled as exc:
        kept_pages = len(completed_pages) if keep_completed_on_failure else 0
        _cleanup_import(project_dir, file_pages, file_assets, file_files)
        if not keep_completed_on_failure:
            _cleanup_import(project_dir, completed_pages, completed_assets, completed_files)
        elif completed_pages:
            _add_import_history(project_dir, len(completed_pages), cancelled=True)
        file_pages, file_assets, file_files = [], [], []
        discard_temporary_uploads(uploads)
        exc.imported_pages = kept_pages  # type: ignore[attr-defined]
        raise
    except Exception as exc:
        kept_pages = len(completed_pages) if keep_completed_on_failure else 0
        _cleanup_import(project_dir, file_pages, file_assets, file_files)
        if not keep_completed_on_failure:
            _cleanup_import(project_dir, completed_pages, completed_assets, completed_files)
        file_pages, file_assets, file_files = [], [], []
        discard_temporary_uploads(uploads)
        exc.imported_pages = kept_pages  # type: ignore[attr-defined]
        raise


def import_files(project_dir: Path, uploads: list[tuple[str, Path]]) -> list[dict[str, Any]]:
    """Synchronous, all-or-nothing import used by simple API clients and tests."""
    return import_uploads(project_dir, uploads, keep_completed_on_failure=False)


def list_pages(project_dir: Path) -> list[dict[str, Any]]:
    with project_db(project_dir) as conn:
        rows = conn.execute("SELECT * FROM pages ORDER BY page_number ASC").fetchall()
    return [_page_payload(row) for row in rows]


def _get_page(conn, page_id: str):
    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if row is None:
        raise AppError(404, "page_not_found", "Page not found.")
    return row


def _asset_path(conn, project_dir: Path, asset_id: str) -> Path:
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise AppError(404, "asset_not_found", "Asset not found.")
    try:
        path = resolve_within(project_dir, row["relative_path"])
    except ValueError as exc:
        raise AppError(500, "asset_path_invalid", "Asset path is invalid.") from exc
    if not path.exists():
        raise AppError(404, "asset_file_missing", "The asset file is missing.")
    return path


def _remove_display_asset(conn, project_dir: Path, page_row) -> None:
    display_id = page_row["display_asset_id"]
    if not display_id:
        return
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (display_id,)).fetchone()
    if row is not None:
        try:
            resolve_within(project_dir, row["relative_path"]).unlink(missing_ok=True)
        except ValueError:
            pass
        conn.execute("DELETE FROM assets WHERE id = ?", (display_id,))
    conn.execute("UPDATE pages SET display_asset_id = NULL WHERE id = ?", (page_row["id"],))


def _update_thumbnail(path: Path, image: Image.Image) -> tuple[int, int, int]:
    return _write_thumbnail(image, path)


def _load_page_source(conn, project_dir: Path, page) -> Image.Image:
    """Return the immutable page source with no processing applied."""
    original_id = page["original_asset_id"]
    if not original_id:
        raise AppError(409, "page_missing_source", "This page has no source image.")
    original_path = _asset_path(conn, project_dir, original_id)

    if page["source_kind"] == "pdf":
        settings = get_settings()
        # Always re-render from the immutable PDF page so repeated edits never
        # accumulate resampling artifacts.
        document = pdf_service.open_document(original_path)
        try:
            index = max(0, int(page["pdf_page_number"] or 1) - 1)
            return pdf_service.render_page(document, index, settings.pdf_render_dpi)
        finally:
            document.close()
    return _load_image(original_path)


def _render_page(source: Image.Image, rotation: int, edits: dict[str, Any]) -> Image.Image:
    rendered = (
        source.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
        if rotation
        else source
    )
    if edits_service.has_edits(edits):
        rendered = edits_service.apply_edits(rendered, edits)
    return rendered


def _needs_display(page, rotation: int, edits: dict[str, Any]) -> bool:
    # PDF pages always need a browser-safe render. Image pages only need a
    # display copy once a transform makes the original unsuitable to show.
    if page["source_kind"] == "pdf":
        return True
    return rotation != 0 or edits_service.has_edits(edits)


def _save_display(
    conn, project_dir: Path, page_id: str, rendered: Image.Image, suffix: str
) -> str:
    display_id = str(uuid.uuid4())
    relative_display = f"processed/{page_id}-{suffix}-{uuid.uuid4().hex[:8]}.png"
    display_path = project_dir / relative_display
    display_path.parent.mkdir(parents=True, exist_ok=True)
    _flatten_for_web(rendered).save(display_path, format="PNG", optimize=False)
    _insert_asset(
        conn,
        asset_id=display_id,
        kind="processed",
        relative_path=relative_display,
        mime_type="image/png",
        byte_size=display_path.stat().st_size,
        checksum=None,
        width=rendered.width,
        height=rendered.height,
    )
    return display_id


def _rerender_page(
    conn,
    project_dir: Path,
    page,
    *,
    rotation: int,
    edits: dict[str, Any],
    suffix: str,
) -> dict[str, Any]:
    """Rebuild the display copy and thumbnail from the immutable source."""
    page_id = page["id"]
    source = _load_page_source(conn, project_dir, page)
    rendered = source
    try:
        rendered = _render_page(source, rotation, edits)
        _remove_display_asset(conn, project_dir, page)

        if _needs_display(page, rotation, edits):
            display_id = _save_display(conn, project_dir, page_id, rendered, suffix)
            width, height = rendered.width, rendered.height
        else:
            display_id = None
            width, height = source.width, source.height

        thumbnail_path = project_dir / "thumbnails" / f"{page_id}.webp"
        thumb_width, thumb_height, thumb_size = _update_thumbnail(thumbnail_path, rendered)
        thumb_asset = conn.execute(
            "SELECT * FROM assets WHERE id = ?", (page["thumbnail_asset_id"],)
        ).fetchone()
        if thumb_asset is not None:
            conn.execute(
                "UPDATE assets SET width = ?, height = ?, byte_size = ? WHERE id = ?",
                (thumb_width, thumb_height, thumb_size, thumb_asset["id"]),
            )

        conn.execute(
            "UPDATE pages SET rotation = ?, width = ?, height = ?, display_asset_id = ?,"
            " edits = ?, updated_at = ? WHERE id = ?",
            (
                rotation,
                width,
                height,
                display_id,
                json.dumps(edits, separators=(",", ":"), sort_keys=True),
                _now(),
                page_id,
            ),
        )
        return _page_payload(
            conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        )
    finally:
        if rendered is not source:
            rendered.close()
        source.close()


def rotate_page(project_dir: Path, page_id: str, degrees: int) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        edits = edits_service.decode_edits(page["edits"])
        total = (int(page["rotation"]) + degrees) % 360
        return _rerender_page(
            conn,
            project_dir,
            page,
            rotation=total,
            edits=edits,
            suffix=f"rotate-{total}",
        )


def update_page_edits(
    project_dir: Path, page_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    edits = edits_service.normalise_edits(payload)
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        row = _rerender_page(
            conn,
            project_dir,
            page,
            rotation=int(page["rotation"]),
            edits=edits,
            suffix="edit",
        )
        conn.execute(
            "INSERT INTO history_events (id, event_type, summary, payload, created_at)"
            " VALUES (?, 'page_processed', ?, '{}', ?)",
            (str(uuid.uuid4()), "Updated page processing", _now()),
        )
        return row


def reset_page_edits(project_dir: Path, page_id: str) -> dict[str, Any]:
    empty = edits_service.normalise_edits({})
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        row = _rerender_page(
            conn,
            project_dir,
            page,
            rotation=int(page["rotation"]),
            edits=empty,
            suffix="reset",
        )
        conn.execute(
            "INSERT INTO history_events (id, event_type, summary, payload, created_at)"
            " VALUES (?, 'page_edits_reset', ?, '{}', ?)",
            (str(uuid.uuid4()), "Reset page processing", _now()),
        )
        return row


def base_page_preview(project_dir: Path, page_id: str) -> Path:
    """Render the rotated page without processing, for before/after comparison."""
    settings = get_settings()
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        source = _load_page_source(conn, project_dir, page)
        rotation = int(page["rotation"])
    try:
        rotated = (
            source.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
            if rotation
            else source
        )
        target = settings.tmp_dir / f"preview-{page_id}-{rotation}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        _flatten_for_web(rotated).save(target, format="PNG", optimize=False)
        if rotated is not source:
            rotated.close()
        return target
    finally:
        source.close()


def estimate_page_skew(project_dir: Path, page_id: str) -> float:
    """Suggest a straightening angle for the current crop/perspective."""
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        edits = edits_service.decode_edits(page["edits"])
        rotation = int(page["rotation"])
        source = _load_page_source(conn, project_dir, page)
    images: list[Image.Image] = [source]
    try:
        current = _render_page(source, rotation, edits_service.geometry_without_deskew(edits))
        if current is not source:
            images.append(current)
        return edits_service.estimate_skew_angle(current)
    finally:
        for image in images:
            image.close()



def delete_page(project_dir: Path, page_id: str) -> None:
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        asset_ids = [
            page["original_asset_id"],
            page["display_asset_id"],
            page["thumbnail_asset_id"],
        ]
        trash_dir = project_dir / "trash" / page_id
        for asset_id in asset_ids:
            if not asset_id:
                continue
            # A PDF's original asset is shared by all of its pages. Only move a
            # file to trash when no other page still references it.
            others = conn.execute(
                """
                SELECT COUNT(*) AS count FROM pages
                WHERE id != ?
                  AND (original_asset_id = ? OR display_asset_id = ? OR thumbnail_asset_id = ?)
                """,
                (page_id, asset_id, asset_id, asset_id),
            ).fetchone()["count"]
            if others:
                continue
            row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if row is None:
                continue
            try:
                path = resolve_within(project_dir, row["relative_path"])
            except ValueError:
                continue
            if path.exists():
                trash_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(trash_dir / path.name))
            conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))

        # Extracted crops depend on this page. Move their files to the same
        # trash folder; the element rows themselves cascade with the page.
        element_assets = conn.execute(
            """
            SELECT assets.* FROM elements
            JOIN assets ON assets.id = elements.asset_id
            WHERE elements.page_id = ?
            """,
            (page_id,),
        ).fetchall()
        for row in element_assets:
            try:
                path = resolve_within(project_dir, row["relative_path"])
            except ValueError:
                path = None
            if path is not None and path.exists():
                trash_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(trash_dir / path.name))
            conn.execute("DELETE FROM assets WHERE id = ?", (row["id"],))

        conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))
        _renumber(conn)
        conn.execute(
            "INSERT INTO history_events (id, event_type, summary, payload, created_at)"
            " VALUES (?, 'page_deleted', ?, '{}', ?)",
            (str(uuid.uuid4()), "Deleted a page", _now()),
        )


def _renumber(conn) -> None:
    rows = conn.execute("SELECT id FROM pages ORDER BY page_number ASC").fetchall()
    conn.execute("UPDATE pages SET page_number = page_number + 100000")
    for index, row in enumerate(rows, start=1):
        conn.execute(
            "UPDATE pages SET page_number = ? WHERE id = ?", (index, row["id"])
        )


def reorder_pages(project_dir: Path, page_ids: list[str]) -> list[dict[str, Any]]:
    with project_db(project_dir) as conn:
        existing = {
            row["id"] for row in conn.execute("SELECT id FROM pages").fetchall()
        }
        if set(page_ids) != existing or len(page_ids) != len(existing):
            raise AppError(
                400,
                "invalid_page_order",
                "The supplied page order must contain every page exactly once.",
            )
        conn.execute("UPDATE pages SET page_number = page_number + 100000")
        for index, page_id in enumerate(page_ids, start=1):
            conn.execute(
                "UPDATE pages SET page_number = ?, updated_at = ? WHERE id = ?",
                (index, _now(), page_id),
            )
        rows = conn.execute("SELECT * FROM pages ORDER BY page_number ASC").fetchall()
    return [_page_payload(row) for row in rows]


def get_asset_file(project_dir: Path, asset_id: str) -> tuple[Path, str]:
    with project_db(project_dir) as conn:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise AppError(404, "asset_not_found", "Asset not found.")
        try:
            path = resolve_within(project_dir, row["relative_path"])
        except ValueError as exc:
            raise AppError(500, "asset_path_invalid", "Asset path is invalid.") from exc
        mime = row["mime_type"] or "application/octet-stream"
    if not path.exists():
        raise AppError(404, "asset_file_missing", "The asset file is missing.")
    return path, mime


def page_bytes_preview(project_dir: Path, page_id: str) -> bytes:
    """Utility used by tests; returns the display bytes for a page."""
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        asset_id = page["display_asset_id"] or page["original_asset_id"]
    path, _mime = get_asset_file(project_dir, asset_id)
    return path.read_bytes()
