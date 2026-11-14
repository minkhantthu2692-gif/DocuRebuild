"""Selective restore from a backup into an existing project.

A full restore always creates a new project. Sometimes only a few pages or one
document version is needed: a page was deleted by mistake, the document was
edited badly, or the rest of the project is fine. This module copies chosen
content out of a validated backup into the current project.

The restore is additive and scoped:

- Pages get new ids and new page numbers after the current last page, so no
  existing page is replaced or renumbered. The page's own assets, OCR runs, OCR
  blocks, AI suggestions and extracted elements are copied with new ids and
  remapped references, so the copied page keeps its text, review status and
  crops.
- A document restore replaces the live document only after the state being
  replaced is snapshotted as a local revision, so it can be undone from the
  version history. The backup's current document or any stored revision can be
  chosen.
- Page restore never touches the document; document restore never touches pages
  or their assets.
- Files are copied under new names, so a missing or different file in the
  current project is never overwritten.
- The archive is extracted once for inspection and kept in a staging folder for
  a short time. The selection is keyed by an opaque token and expires, so a
  forgotten dialog cannot leave a large extraction behind indefinitely.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import atomic_write_json, resolve_within
from app.db.models import Project
from app.db.project_schema import project_db, utc_iso
from app.services import documents, project_backup
from app.services import projects as project_service

SELECTION_PREFIX = "select-"
SELECTION_VERSION = 2
# Long enough to review a large page list, short enough that an abandoned
# extraction does not sit in tmp for a whole session.
SELECTION_TTL_SECONDS = 60 * 60
MAX_SELECTED_PAGES = 5000
DOCUMENT_PREVIEW_LENGTH = 200
# Page image slots in display order. The database column keeps the reference.
ASSET_SLOTS = (
    ("original", "original_asset_id"),
    ("display", "display_asset_id"),
    ("thumbnail", "thumbnail_asset_id"),
)
_TOKEN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class Selection:
    token: str
    directory: Path
    source_name: str
    created_at: str
    pages: list[dict[str, Any]]
    document: dict[str, Any]


def _expired() -> AppError:
    return AppError(
        410,
        "restore_selection_expired",
        "This page selection has expired. Inspect the backup again.",
    )


def _open_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def _created_at(manifest: dict[str, Any]) -> str:
    value = manifest.get("created_at")
    return value if isinstance(value, str) else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_path(base: Path, relative: Any) -> Path | None:
    """Resolve an asset path inside a project folder, or None when unsafe."""
    if not isinstance(relative, str) or not relative:
        return None
    try:
        return resolve_within(base, relative)
    except ValueError:
        return None


def _missing_asset(
    connection: sqlite3.Connection, base: Path, asset_id: str | None
) -> bool:
    """True when a page slot cannot show its image.

    A slot is missing when it has no id, its asset row is gone, its path is
    unsafe, or the file is missing or empty. Anything else is left alone.
    """
    if not asset_id:
        return True
    row = connection.execute(
        "SELECT relative_path FROM assets WHERE id = ?", (asset_id,)
    ).fetchone()
    if row is None:
        return True
    path = _asset_path(base, row["relative_path"])
    if path is None or not path.is_file():
        return True
    try:
        return path.stat().st_size == 0
    except OSError:
        return True


def _available_asset(
    connection: sqlite3.Connection, base: Path, asset_id: str | None
) -> bool:
    """True when the backup can supply this slot's file."""
    return bool(asset_id) and not _missing_asset(connection, base, asset_id)


def _page_asset_status(
    connection: sqlite3.Connection, base: Path, page: sqlite3.Row
) -> list[str]:
    """Slot names whose image is missing in this project.

    A null display slot is normal: most imports use the original directly and
    only converted formats get a separate display file. It is therefore not
    reported as missing on its own.
    """
    return [
        slot
        for slot, column in ASSET_SLOTS
        if not (slot == "display" and page[column] is None)
        and _missing_asset(connection, base, page[column])
    ]


def _list_pages(staging: Path, project_dir: Path) -> list[dict[str, Any]]:
    """List backup pages, annotated with what this project is missing.

    The current project database is opened read-only and best effort: if it is
    absent or unreadable, every page is reported as not in this project instead
    of failing the inspection.
    """
    database_path = staging / "project.db"
    current: sqlite3.Connection | None = None
    current_path = project_dir / "project.db"
    if current_path.is_file():
        try:
            current = _open_readonly(current_path)
        except sqlite3.DatabaseError:
            current = None

    try:
        connection = _open_readonly(database_path)
        try:
            rows = connection.execute(
                "SELECT id, page_number, source_kind, status, width, height,"
                " original_filename, original_asset_id, display_asset_id,"
                " thumbnail_asset_id FROM pages ORDER BY page_number ASC"
            ).fetchall()
            pages: list[dict[str, Any]] = []
            for row in rows:
                in_project = False
                missing_slots: list[str] = []
                restorable_slots: list[str] = []
                if current is not None:
                    try:
                        existing = current.execute(
                            "SELECT * FROM pages WHERE id = ?", (row["id"],)
                        ).fetchone()
                        if existing is not None:
                            in_project = True
                            missing_slots = _page_asset_status(
                                current, project_dir, existing
                            )
                            restorable_slots = [
                                slot
                                for slot in missing_slots
                                if _available_asset(
                                    connection, staging, row[f"{slot}_asset_id"]
                                )
                            ]
                    except (sqlite3.DatabaseError, IndexError):
                        # An unreadable or older current database must not stop
                        # the inspection; report the page as not in this project.
                        current.close()
                        current = None
                        in_project = False
                        missing_slots = []
                        restorable_slots = []
                pages.append(
                    {
                        "id": row["id"],
                        "page_number": row["page_number"],
                        "source_kind": row["source_kind"],
                        "status": row["status"],
                        "width": row["width"],
                        "height": row["height"],
                        "original_filename": row["original_filename"],
                        "in_project": in_project,
                        "missing_slots": missing_slots,
                        "restorable_slots": restorable_slots,
                    }
                )
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise AppError(
            422,
            "backup_database_invalid",
            "The project database in the backup cannot be read.",
        ) from exc
    finally:
        if current is not None:
            current.close()
    return pages


def _preview(plain_text: str) -> str:
    return " ".join(plain_text.split())[:DOCUMENT_PREVIEW_LENGTH]


def _list_document(database_path: Path) -> dict[str, Any]:
    """Summarise the backup's live document and its stored revisions."""
    try:
        connection = _open_readonly(database_path)
        try:
            current = connection.execute(
                "SELECT plain_text, updated_at FROM documents WHERE id = 'main'"
            ).fetchone()
            revisions = connection.execute(
                "SELECT id, source, plain_text, created_at FROM document_revisions"
                " ORDER BY created_at DESC, rowid DESC LIMIT 100"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise AppError(
            422,
            "backup_database_invalid",
            "The project database in the backup cannot be read.",
        ) from exc

    current_text = str(current["plain_text"]) if current is not None else ""
    return {
        "current": {
            "preview": _preview(current_text),
            "character_count": len(current_text),
            "updated_at": (
                str(current["updated_at"])
                if current is not None and current["updated_at"]
                else None
            ),
        },
        "revisions": [
            {
                "id": row["id"],
                "source": row["source"],
                "preview": _preview(str(row["plain_text"])),
                "character_count": len(str(row["plain_text"])),
                "created_at": row["created_at"],
            }
            for row in revisions
        ],
    }


def _cleanup_stale() -> None:
    """Remove abandoned selections after the time-to-live, best effort."""
    folder = get_settings().tmp_dir
    if not folder.is_dir():
        return
    cutoff = time.time() - SELECTION_TTL_SECONDS
    for candidate in folder.glob(f"{SELECTION_PREFIX}*"):
        try:
            if candidate.is_dir() and not candidate.is_symlink():
                if candidate.stat().st_mtime < cutoff:
                    shutil.rmtree(candidate, ignore_errors=True)
        except OSError:
            continue


def inspect(
    archive_path: Path, *, project_id: str, source_name: str, project_dir: Path
) -> dict[str, Any]:
    """Extract and validate an archive, then list pages and document versions."""
    extracted = project_backup.extract_validated(archive_path)
    staging = extracted.directory
    try:
        pages = _list_pages(staging, project_dir)
        document = _list_document(staging / "project.db")
        if len(pages) > MAX_SELECTED_PAGES:
            raise AppError(
                422,
                "backup_too_many_pages",
                "This backup has more pages than a selective restore supports.",
            )
        token = uuid.uuid4().hex
        payload = {
            "version": SELECTION_VERSION,
            "project_id": project_id,
            "source_name": source_name,
            "created_at": _created_at(extracted.manifest),
            "pages": pages,
            "document": document,
        }
        atomic_write_json(staging / "selection.json", payload)
        staging.rename(staging.with_name(f"{SELECTION_PREFIX}{token}"))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    _cleanup_stale()
    return {
        "token": token,
        "source_name": source_name,
        "created_at": payload["created_at"],
        "pages": pages,
        "document": document,
    }


def load(token: str, *, project_id: str) -> Selection:
    """Return a live selection or a typed error the dialog can explain."""
    if not _TOKEN.fullmatch(token):
        raise _expired()
    directory = get_settings().tmp_dir / f"{SELECTION_PREFIX}{token}"
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise _expired()
        if time.time() - directory.stat().st_mtime > SELECTION_TTL_SECONDS:
            shutil.rmtree(directory, ignore_errors=True)
            raise _expired()
        payload = json.loads((directory / "selection.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _expired() from exc

    if (
        not isinstance(payload, dict)
        or payload.get("version") != SELECTION_VERSION
        or payload.get("project_id") != project_id
    ):
        raise _expired()
    pages = payload.get("pages")
    document = payload.get("document")
    if not isinstance(pages, list) or not isinstance(document, dict):
        raise _expired()
    return Selection(
        token=token,
        directory=directory,
        source_name=str(payload.get("source_name") or "backup"),
        created_at=str(payload.get("created_at") or ""),
        pages=pages,
        document=document,
    )


def discard(token: str) -> None:
    """Remove the staged archive once the selection is applied or abandoned."""
    if not _TOKEN.fullmatch(token):
        return
    shutil.rmtree(
        get_settings().tmp_dir / f"{SELECTION_PREFIX}{token}", ignore_errors=True
    )


def _insert(connection: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def _new_id() -> str:
    return str(uuid.uuid4())


def _copy_asset(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    staging: Path,
    project_dir: Path,
    old_id: str | None,
    asset_map: dict[str, str],
    created_files: list[Path],
) -> str | None:
    """Copy one asset row and its file under a new id, or return None."""
    if not old_id:
        return None
    if old_id in asset_map:
        return asset_map[old_id]
    row = source.execute("SELECT * FROM assets WHERE id = ?", (old_id,)).fetchone()
    if row is None:
        return None
    new_id = _new_id()
    relative = str(row["relative_path"])
    pure = PurePosixPath(relative)
    new_relative = str(pure.with_name(f"{new_id}{pure.suffix}"))
    try:
        source_path = resolve_within(staging, relative)
        target_path = resolve_within(project_dir, new_relative)
    except ValueError as exc:
        raise AppError(
            422,
            "backup_unsafe_path",
            "A page file in the backup has an unsafe path.",
        ) from exc
    if not source_path.is_file():
        raise AppError(
            422,
            "backup_missing_files",
            "A page image in the backup is missing.",
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_path)
    created_files.append(target_path)

    values = dict(row)
    values.update(id=new_id, relative_path=new_relative)
    _insert(target, "assets", values)
    asset_map[old_id] = new_id
    return new_id


def _copy_page(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    staging: Path,
    project_dir: Path,
    page_id: str,
    page_number: int,
    created_files: list[Path],
) -> None:
    page = source.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if page is None:
        raise AppError(
            422,
            "page_selection_invalid",
            "One or more selected pages are not in this backup.",
        )

    asset_map: dict[str, str] = {}
    original = _copy_asset(
        source, target, staging, project_dir, page["original_asset_id"], asset_map, created_files
    )
    display = _copy_asset(
        source, target, staging, project_dir, page["display_asset_id"], asset_map, created_files
    )
    thumbnail = _copy_asset(
        source, target, staging, project_dir, page["thumbnail_asset_id"], asset_map, created_files
    )

    new_page_id = _new_id()
    page_values = dict(page)
    page_values.update(
        id=new_page_id,
        page_number=page_number,
        original_asset_id=original,
        display_asset_id=display,
        thumbnail_asset_id=thumbnail,
    )
    _insert(target, "pages", page_values)

    runs = source.execute(
        "SELECT * FROM ocr_runs WHERE page_id = ? ORDER BY created_at ASC, id ASC",
        (page_id,),
    ).fetchall()
    for run in runs:
        new_run_id = _new_id()
        run_values = dict(run)
        run_values.update(
            id=new_run_id,
            page_id=new_page_id,
            source_asset_id=(
                asset_map.get(run["source_asset_id"]) if run["source_asset_id"] else None
            ),
        )
        _insert(target, "ocr_runs", run_values)

        blocks = source.execute(
            "SELECT * FROM ocr_blocks WHERE run_id = ? ORDER BY block_index ASC, id ASC",
            (run["id"],),
        ).fetchall()
        for block in blocks:
            new_block_id = _new_id()
            block_values = dict(block)
            block_values.update(id=new_block_id, run_id=new_run_id, page_id=new_page_id)
            _insert(target, "ocr_blocks", block_values)

            suggestions = source.execute(
                "SELECT * FROM ai_suggestions WHERE block_id = ?"
                " ORDER BY created_at ASC, id ASC",
                (block["id"],),
            ).fetchall()
            for suggestion in suggestions:
                suggestion_values = dict(suggestion)
                suggestion_values.update(
                    id=_new_id(), page_id=new_page_id, block_id=new_block_id
                )
                _insert(target, "ai_suggestions", suggestion_values)

    elements = source.execute(
        "SELECT * FROM elements WHERE page_id = ? ORDER BY created_at ASC, id ASC",
        (page_id,),
    ).fetchall()
    for element in elements:
        element_values = dict(element)
        element_values.update(
            id=_new_id(),
            page_id=new_page_id,
            asset_id=_copy_asset(
                source,
                target,
                staging,
                project_dir,
                element["asset_id"],
                asset_map,
                created_files,
            ),
            source_asset_id=(
                asset_map.get(element["source_asset_id"])
                if element["source_asset_id"]
                else None
            ),
        )
        _insert(target, "elements", element_values)


def apply(
    project: Project, selection: Selection, page_ids: list[str]
) -> dict[str, Any]:
    """Append the selected pages to the project and return what was restored."""
    chosen = {page_id for page_id in page_ids if isinstance(page_id, str)}
    if not chosen:
        raise AppError(
            422, "page_selection_empty", "Select at least one page to restore."
        )
    available = {str(page["id"]) for page in selection.pages}
    if not chosen.issubset(available):
        raise AppError(
            422,
            "page_selection_invalid",
            "One or more selected pages are not in this backup.",
        )
    ordered = [page for page in selection.pages if str(page["id"]) in chosen]
    if len(ordered) > MAX_SELECTED_PAGES:
        raise AppError(
            422,
            "backup_too_many_pages",
            "Too many pages were selected for one restore.",
        )

    project_dir = Path(project.directory)
    staged_database = selection.directory / "project.db"
    created_files: list[Path] = []
    page_numbers: list[int] = []

    source = _open_readonly(staged_database)
    try:
        with project_db(project_dir) as target:
            row = target.execute(
                "SELECT COALESCE(MAX(page_number), 0) + 1 AS next FROM pages"
            ).fetchone()
            next_number = int(row["next"])
            for page in ordered:
                _copy_page(
                    source,
                    target,
                    selection.directory,
                    project_dir,
                    str(page["id"]),
                    next_number,
                    created_files,
                )
                page_numbers.append(next_number)
                next_number += 1
    except Exception:
        for path in created_files:
            path.unlink(missing_ok=True)
        raise
    finally:
        source.close()

    project_service.record_history(
        project_dir,
        "pages_restored",
        "Pages restored from backup",
        {
            "count": len(page_numbers),
            "source": selection.source_name,
            "page_numbers": page_numbers,
        },
    )
    return {"restored": len(page_numbers), "page_numbers": page_numbers}


def apply_document(
    project: Project, selection: Selection, revision_id: str | None
) -> dict[str, Any]:
    """Replace the live document with the backup's current text or one revision.

    The replaced state is snapshotted first, so this action can itself be undone
    from the local version history.
    """
    staged_database = selection.directory / "project.db"
    source = _open_readonly(staged_database)
    try:
        if revision_id is None:
            row = source.execute(
                "SELECT content, plain_text FROM documents WHERE id = 'main'"
            ).fetchone()
            kind = "current"
        else:
            row = source.execute(
                "SELECT content, plain_text FROM document_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
            kind = "revision"
    except sqlite3.DatabaseError as exc:
        raise AppError(
            422,
            "backup_database_invalid",
            "The project database in the backup cannot be read.",
        ) from exc
    finally:
        source.close()

    if row is None:
        raise AppError(
            422,
            "backup_document_missing",
            "The selected document version is not in this backup.",
        )
    try:
        content = json.loads(row["content"])
    except (TypeError, ValueError) as exc:
        raise AppError(
            422,
            "backup_document_invalid",
            "The document in this backup cannot be read.",
        ) from exc
    if not isinstance(content, dict) or content.get("type") != "doc":
        raise AppError(
            422,
            "backup_document_invalid",
            "The document in this backup cannot be read.",
        )

    plain_text = str(row["plain_text"])
    project_dir = Path(project.directory)
    document = documents.replace_document(project_dir, content, plain_text)
    project_service.record_history(
        project_dir,
        "document_restored",
        "Document restored from backup",
        {
            "source": selection.source_name,
            "document_source": kind,
            "revision_id": revision_id,
            "character_count": len(plain_text),
        },
    )
    return {
        "restored": True,
        "source": kind,
        "revision_id": revision_id,
        "updated_at": document["updated_at"],
        "document": document,
    }


def _backup_asset_file(
    source: sqlite3.Connection, staging: Path, asset_id: str | None
) -> tuple[sqlite3.Row, Path] | None:
    """Return a backup asset row and its verified file, or None when unusable."""
    if not asset_id:
        return None
    row = source.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        return None
    path = _asset_path(staging, row["relative_path"])
    if path is None or not path.is_file():
        return None
    try:
        if path.stat().st_size == 0:
            return None
    except OSError:
        return None
    checksum = row["checksum"]
    if checksum and _sha256(path) != checksum:
        raise AppError(
            422,
            "backup_checksum_mismatch",
            "A page image in the backup does not match its checksum.",
        )
    return row, path


def _restore_asset_in_place(
    target: sqlite3.Connection,
    project_dir: Path,
    asset_id: str,
    backup: sqlite3.Row,
    source_path: Path,
) -> None:
    """Rewrite the file under an existing asset id, keeping references valid.

    The asset row is kept so OCR ``source_asset_id`` and element references do
    not become stale. If the row's stored path is unsafe, the id is kept but the
    path is replaced with a safe name derived from the backup file.
    """
    row = target.execute(
        "SELECT relative_path FROM assets WHERE id = ?", (asset_id,)
    ).fetchone()
    relative = row["relative_path"] if row is not None else None
    target_path = _asset_path(project_dir, relative)
    if target_path is None:
        pure = PurePosixPath(str(backup["relative_path"]))
        relative = str(pure.with_name(f"{asset_id}{pure.suffix}"))
        target_path = resolve_within(project_dir, relative)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_path)
    target.execute(
        "UPDATE assets SET relative_path = ?, mime_type = ?, byte_size = ?,"
        " checksum = ?, width = ?, height = ? WHERE id = ?",
        (
            relative,
            backup["mime_type"],
            source_path.stat().st_size,
            backup["checksum"],
            backup["width"],
            backup["height"],
            asset_id,
        ),
    )


def apply_page_assets(
    project: Project, selection: Selection, page_id: str
) -> dict[str, Any]:
    """Restore missing image files for one existing page from the backup.

    Only slots whose image is missing are touched. A present image is never
    overwritten, and the page, its OCR runs and its elements keep their ids.
    """
    if page_id not in {str(page["id"]) for page in selection.pages}:
        raise AppError(
            422,
            "page_selection_invalid",
            "The selected page is not in this backup.",
        )

    project_dir = Path(project.directory)
    staged_database = selection.directory / "project.db"
    created_files: list[Path] = []
    restored: list[str] = []
    page_number = 0

    source = _open_readonly(staged_database)
    try:
        with project_db(project_dir) as target:
            current = target.execute(
                "SELECT * FROM pages WHERE id = ?", (page_id,)
            ).fetchone()
            if current is None:
                raise AppError(
                    422,
                    "page_not_in_project",
                    "This page is not in the current project.",
                )
            page_number = int(current["page_number"])
            backup = source.execute(
                "SELECT * FROM pages WHERE id = ?", (page_id,)
            ).fetchone()
            if backup is None:
                raise AppError(
                    422,
                    "page_selection_invalid",
                    "The selected page is not in this backup.",
                )

            for slot, column in ASSET_SLOTS:
                if not _missing_asset(target, project_dir, current[column]):
                    continue
                found = _backup_asset_file(
                    source, selection.directory, backup[column]
                )
                if found is None:
                    continue
                backup_asset, source_path = found
                current_id = current[column]
                existing = (
                    target.execute(
                        "SELECT 1 FROM assets WHERE id = ?", (current_id,)
                    ).fetchone()
                    if current_id
                    else None
                )
                if existing is not None:
                    _restore_asset_in_place(
                        target, project_dir, current_id, backup_asset, source_path
                    )
                else:
                    new_id = _copy_asset(
                        source,
                        target,
                        selection.directory,
                        project_dir,
                        backup[column],
                        {},
                        created_files,
                    )
                    if not new_id:
                        continue
                    target.execute(
                        f"UPDATE pages SET {column} = ? WHERE id = ?",
                        (new_id, page_id),
                    )
                restored.append(slot)

            if restored:
                target.execute(
                    "UPDATE pages SET updated_at = ? WHERE id = ?",
                    (utc_iso(), page_id),
                )
    except Exception:
        for path in created_files:
            path.unlink(missing_ok=True)
        raise
    finally:
        source.close()

    if restored:
        project_service.record_history(
            project_dir,
            "page_assets_restored",
            "Page image repaired from backup",
            {
                "page_id": page_id,
                "page_number": page_number,
                "slots": restored,
                "source": selection.source_name,
            },
        )
    return {
        "page_id": page_id,
        "page_number": page_number,
        "restored_slots": restored,
    }
