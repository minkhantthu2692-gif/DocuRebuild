from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import AppError
from app.core.storage import resolve_within
from app.db.project_schema import project_db, utc_iso

logger = logging.getLogger(__name__)

THUMBNAIL_EDGE = 480

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

Image.MAX_IMAGE_PIXELS = 180_000_000


def _now() -> str:
    return utc_iso()


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


def import_images(project_dir: Path, uploads: list[tuple[str, Path]]) -> list[dict[str, Any]]:
    """Import validated temporary image files as immutable source pages.

    Each source file is stored once under ``source/`` and never modified again.
    """
    if not uploads:
        raise AppError(400, "no_files", "No files were provided.")

    # Validate every file before mutating the project so a bad file cannot
    # leave a half-imported batch.
    inspected: list[tuple[str, Path, str, int, int, int]] = []
    for filename, temp_path in uploads:
        extension = validate_image_name(filename)
        try:
            image = _load_image(temp_path)
        except AppError:
            raise AppError(422, "image_unreadable", f"'{filename}' is not a readable image.")
        inspected.append((filename, temp_path, extension, image.width, image.height, 0))
        image.close()

    imported: list[dict[str, Any]] = []
    try:
        with project_db(project_dir) as conn:
            next_number = (
                conn.execute(
                    "SELECT COALESCE(MAX(page_number), 0) + 1 AS next FROM pages"
                ).fetchone()["next"]
            )
            for index, (filename, temp_path, extension, width, height, _) in enumerate(inspected):
                page_id = str(uuid.uuid4())
                original_id = str(uuid.uuid4())
                thumbnail_id = str(uuid.uuid4())
                relative_source = f"source/{original_id}{extension}"
                source_path = project_dir / relative_source
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(temp_path), str(source_path))

                image = _load_image(source_path)
                display_id: str | None = None
                display_width, display_height = image.width, image.height

                if extension in CONVERTED_EXTENSIONS:
                    display_id = str(uuid.uuid4())
                    relative_display = f"processed/{page_id}-display.png"
                    display_path = project_dir / relative_display
                    display_path.parent.mkdir(parents=True, exist_ok=True)
                    _flatten_for_web(image).save(display_path, format="PNG", optimize=False)
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

                thumb_width, thumb_height, thumb_size = _write_thumbnail(
                    image, project_dir / "thumbnails" / f"{page_id}.webp"
                )
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
                    relative_path=f"thumbnails/{page_id}.webp",
                    mime_type="image/webp",
                    byte_size=thumb_size,
                    checksum=None,
                    width=thumb_width,
                    height=thumb_height,
                )

                now = _now()
                page_number = int(next_number) + index
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
                row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
                imported.append(dict(row))

            conn.execute(
                "INSERT INTO history_events (id, event_type, summary, payload, created_at)"
                " VALUES (?, 'pages_imported', ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    f"Imported {len(imported)} page(s)",
                    "{}",
                    _now(),
                ),
            )
    except Exception:
        for filename, temp_path, *_ in inspected:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        raise
    return imported


def list_pages(project_dir: Path) -> list[dict[str, Any]]:
    with project_db(project_dir) as conn:
        rows = conn.execute("SELECT * FROM pages ORDER BY page_number ASC").fetchall()
    return [dict(row) for row in rows]


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


def rotate_page(project_dir: Path, page_id: str, degrees: int) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        original_id = page["original_asset_id"]
        if not original_id:
            raise AppError(409, "page_missing_source", "This page has no source image.")
        original_path = _asset_path(conn, project_dir, original_id)
        image = _load_image(original_path)
        total = (int(page["rotation"]) + degrees) % 360

        thumbnail_path = project_dir / "thumbnails" / f"{page_id}.webp"
        thumb_asset = conn.execute(
            "SELECT * FROM assets WHERE id = ?", (page["thumbnail_asset_id"],)
        ).fetchone()

        _remove_display_asset(conn, project_dir, page)

        if total == 0:
            display_id = None
            width, height = image.width, image.height
            rendered = image
        else:
            rendered = image.rotate(total, expand=True, resample=Image.Resampling.BICUBIC)
            display_id = str(uuid.uuid4())
            relative_display = f"processed/{page_id}-rotate-{total}.png"
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
            width, height = rendered.width, rendered.height

        thumb_width, thumb_height, thumb_size = _update_thumbnail(thumbnail_path, rendered)
        if thumb_asset is not None:
            conn.execute(
                "UPDATE assets SET width = ?, height = ?, byte_size = ? WHERE id = ?",
                (thumb_width, thumb_height, thumb_size, thumb_asset["id"]),
            )
        image.close()
        if rendered is not image:
            rendered.close()

        conn.execute(
            "UPDATE pages SET rotation = ?, width = ?, height = ?, display_asset_id = ?,"
            " updated_at = ? WHERE id = ?",
            (total, width, height, display_id, _now(), page_id),
        )
        row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        return dict(row)


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
        conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))
        for asset_id in asset_ids:
            if asset_id:
                conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
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
    return [dict(row) for row in rows]


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
