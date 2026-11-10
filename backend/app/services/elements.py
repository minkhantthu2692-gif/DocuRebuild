from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.errors import AppError
from app.core.storage import resolve_within
from app.db.project_schema import project_db, utc_iso
from app.services import ocr as ocr_service
from app.services import pages as page_service

ELEMENT_KINDS = ("figure", "table", "equation")
MIN_REGION_SIDE = 8
MAX_CAPTION_LENGTH = 500
MAX_TEXT_LENGTH = 20_000


def _now() -> str:
    return utc_iso()


def _current_asset_id(conn, page_row) -> str | None:
    return page_row["display_asset_id"] or page_row["original_asset_id"]


def _element_payload(row, current_asset_id: str | None) -> dict[str, Any]:
    source_asset_id = row["source_asset_id"]
    return {
        "id": row["id"],
        "page_id": row["page_id"],
        "kind": row["kind"],
        "asset_id": row["asset_id"],
        "x": row["x"],
        "y": row["y"],
        "width": row["width"],
        "height": row["height"],
        "caption": row["caption"],
        "source": row["source"],
        "verified": bool(row["verified"]),
        "text": row["text"],
        "text_confidence": row["text_confidence"],
        "text_engine": row["text_engine"],
        "text_engine_version": row["text_engine_version"],
        "text_languages": [
            item for item in (row["text_languages"] or "").split("+") if item
        ],
        "text_corrected": bool(row["text_corrected"]),
        "text_updated_at": row["text_updated_at"],
        # The crop itself is immutable, but it was taken from an earlier
        # rendered version of the page. Surface that instead of pretending the
        # element still matches the current page.
        "stale": bool(source_asset_id) and source_asset_id != current_asset_id,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _get_page(conn, page_id: str):
    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if row is None:
        raise AppError(404, "page_not_found", "Page not found.")
    return row


def _get_element_row(conn, element_id: str):
    row = conn.execute("SELECT * FROM elements WHERE id = ?", (element_id,)).fetchone()
    if row is None:
        raise AppError(404, "element_not_found", "Extracted element not found.")
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


def _history(conn, event_type: str, summary: str) -> None:
    conn.execute(
        "INSERT INTO history_events (id, event_type, summary, payload, created_at)"
        " VALUES (?, ?, ?, '{}', ?)",
        (str(uuid.uuid4()), event_type, summary, _now()),
    )


def list_elements(project_dir: Path, page_id: str) -> list[dict[str, Any]]:
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        rows = conn.execute(
            "SELECT * FROM elements WHERE page_id = ? ORDER BY created_at DESC",
            (page_id,),
        ).fetchall()
        current_asset_id = _current_asset_id(conn, page)
        return [_element_payload(row, current_asset_id) for row in rows]


def _validate_region(
    x: int, y: int, width: int, height: int, image_width: int, image_height: int
) -> None:
    if width < MIN_REGION_SIDE or height < MIN_REGION_SIDE:
        raise AppError(
            422,
            "element_region_too_small",
            f"Select a region of at least {MIN_REGION_SIDE} x {MIN_REGION_SIDE} pixels.",
        )
    if x < 0 or y < 0:
        raise AppError(
            422, "element_region_invalid", "The selected region starts outside the page."
        )
    if x + width > image_width or y + height > image_height:
        raise AppError(
            422,
            "element_region_invalid",
            "The selected region extends beyond the page image.",
        )


def create_element(
    project_dir: Path,
    page_id: str,
    *,
    kind: str,
    x: int,
    y: int,
    width: int,
    height: int,
    caption: str,
) -> dict[str, Any]:
    if kind not in ELEMENT_KINDS:
        raise AppError(422, "element_kind_invalid", "Unsupported element kind.")
    caption = caption.strip()
    if len(caption) > MAX_CAPTION_LENGTH:
        raise AppError(
            422,
            "element_caption_too_long",
            f"Captions may be at most {MAX_CAPTION_LENGTH} characters.",
        )

    element_id = str(uuid.uuid4())
    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        source_asset_id = _current_asset_id(conn, page)
        if not source_asset_id:
            raise AppError(409, "page_missing_source", "This page has no source image.")
        source_path = _asset_path(conn, project_dir, source_asset_id)
        source = page_service._load_image(source_path)

        try:
            _validate_region(x, y, width, height, source.width, source.height)
            crop = source.crop((x, y, x + width, y + height))
            try:
                relative_path = f"processed/elements/{element_id}.png"
                target = project_dir / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                flattened = page_service._flatten_for_web(crop)
                try:
                    flattened.save(target, format="PNG", optimize=False)
                finally:
                    if flattened is not crop:
                        flattened.close()
                byte_size = target.stat().st_size
            finally:
                crop.close()
        finally:
            source.close()

        now = _now()
        conn.execute(
            """
            INSERT INTO assets (id, kind, relative_path, mime_type, byte_size, checksum,
                                width, height, created_at)
            VALUES (?, 'extracted', ?, 'image/png', ?, NULL, ?, ?, ?)
            """,
            (
                element_id,
                relative_path,
                byte_size,
                width,
                height,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO elements (id, page_id, kind, asset_id, source_asset_id,
                                  x, y, width, height, caption, source, verified,
                                  created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', 0, ?, ?)
            """,
            (
                element_id,
                page_id,
                kind,
                element_id,
                source_asset_id,
                x,
                y,
                width,
                height,
                caption,
                now,
                now,
            ),
        )
        _history(conn, "element_extracted", f"Extracted a {kind} region")
        row = _get_element_row(conn, element_id)
        return _element_payload(row, _current_asset_id(conn, _get_page(conn, page_id)))


def update_element(
    project_dir: Path,
    element_id: str,
    *,
    caption: str | None = None,
    verified: bool | None = None,
) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        row = _get_element_row(conn, element_id)
        updates: list[str] = []
        values: list[Any] = []
        if caption is not None:
            caption = caption.strip()
            if len(caption) > MAX_CAPTION_LENGTH:
                raise AppError(
                    422,
                    "element_caption_too_long",
                    f"Captions may be at most {MAX_CAPTION_LENGTH} characters.",
                )
            updates.append("caption = ?")
            values.append(caption)
        if verified is not None:
            updates.append("verified = ?")
            values.append(1 if verified else 0)
        if updates:
            updates.append("updated_at = ?")
            values.append(_now())
            values.append(element_id)
            conn.execute(
                f"UPDATE elements SET {', '.join(updates)} WHERE id = ?",  # noqa: S608
                values,
            )
            _history(conn, "element_updated", "Updated an extracted element")
        updated = _get_element_row(conn, element_id)
        page = _get_page(conn, updated["page_id"])
        return _element_payload(updated, _current_asset_id(conn, page))


def _normalise_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def extract_element_text(
    project_dir: Path, element_id: str, languages: list[str]
) -> dict[str, Any]:
    """Run local OCR on the immutable crop and store the result as a proposal."""
    with project_db(project_dir) as conn:
        row = _get_element_row(conn, element_id)
        if not row["asset_id"]:
            raise AppError(
                409,
                "element_has_no_crop",
                "This extracted element has no crop image to read.",
            )
        image_path = _asset_path(conn, project_dir, row["asset_id"])

    # OCR can take seconds. Never hold the SQLite transaction open while the
    # local engine runs; re-read the row afterwards in case it was deleted.
    result = ocr_service.extract_image_text(image_path, languages)

    with project_db(project_dir) as conn:
        # Fail cleanly if the element was deleted while the engine was running.
        _get_element_row(conn, element_id)
        now = _now()
        conn.execute(
            """
            UPDATE elements
            SET text = ?, text_confidence = ?, text_engine = ?,
                text_engine_version = ?, text_languages = ?, text_corrected = 0,
                text_updated_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                _normalise_text(result["text"]),
                result["confidence"],
                result["engine"],
                result["engine_version"],
                "+".join(result["languages"]),
                now,
                now,
                element_id,
            ),
        )
        _history(conn, "element_text_extracted", "Extracted text from an element crop")
        updated = _get_element_row(conn, element_id)
        page = _get_page(conn, updated["page_id"])
        return _element_payload(updated, _current_asset_id(conn, page))


def update_element_text(
    project_dir: Path, element_id: str, text: str
) -> dict[str, Any]:
    """Store a reviewed or manually corrected text for an element."""
    text = _normalise_text(text)
    if len(text) > MAX_TEXT_LENGTH:
        raise AppError(
            422,
            "element_text_too_long",
            f"Extracted text may be at most {MAX_TEXT_LENGTH} characters.",
        )
    with project_db(project_dir) as conn:
        row = _get_element_row(conn, element_id)
        if text != row["text"]:
            now = _now()
            conn.execute(
                """
                UPDATE elements
                SET text = ?, text_corrected = 1, text_updated_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (text, now, now, element_id),
            )
            _history(conn, "element_text_updated", "Corrected an element's extracted text")
        updated = _get_element_row(conn, element_id)
        page = _get_page(conn, updated["page_id"])
        return _element_payload(updated, _current_asset_id(conn, page))


def delete_element(project_dir: Path, element_id: str) -> None:
    with project_db(project_dir) as conn:
        row = _get_element_row(conn, element_id)
        asset_id = row["asset_id"]
        if asset_id:
            asset = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if asset is not None:
                try:
                    path = resolve_within(project_dir, asset["relative_path"])
                except ValueError:
                    path = None
                if path is not None and path.exists():
                    trash_dir = project_dir / "trash" / "elements" / element_id
                    trash_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(trash_dir / path.name))
                conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        conn.execute("DELETE FROM elements WHERE id = ?", (element_id,))
        _history(conn, "element_deleted", "Deleted an extracted element")
