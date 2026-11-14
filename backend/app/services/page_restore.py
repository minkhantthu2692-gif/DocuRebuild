"""Selective restore of pages from a backup into an existing project.

A full restore always creates a new project. Sometimes only a few pages are
needed: a page was deleted by mistake, or a page was damaged while the rest of
the project is fine. This module copies chosen pages out of a validated backup
and appends them to the current project.

The restore is additive and page-scoped:

- Pages get new ids and new page numbers after the current last page, so no
  existing page is replaced or renumbered.
- The page's own assets, OCR runs, OCR blocks, AI suggestions and extracted
  elements are copied with new ids and remapped references, so the copied page
  keeps its text, review status and crops.
- The document is never touched. Figure or equation references in the text stay
  exactly as they are; copying a page cannot silently rewrite prose.
- Files are copied under new names, so a missing or different file in the
  current project is never overwritten.
- The archive is extracted once for inspection and kept in a staging folder for
  a short time. The selection is keyed by an opaque token and expires, so a
  forgotten dialog cannot leave a large extraction behind indefinitely.
"""

from __future__ import annotations

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
from app.db.project_schema import project_db
from app.services import project_backup
from app.services import projects as project_service

SELECTION_PREFIX = "select-"
SELECTION_VERSION = 1
# Long enough to review a large page list, short enough that an abandoned
# extraction does not sit in tmp for a whole session.
SELECTION_TTL_SECONDS = 60 * 60
MAX_SELECTED_PAGES = 5000
_TOKEN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class Selection:
    token: str
    directory: Path
    source_name: str
    created_at: str
    pages: list[dict[str, Any]]


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


def _list_pages(database_path: Path) -> list[dict[str, Any]]:
    try:
        connection = _open_readonly(database_path)
        try:
            rows = connection.execute(
                "SELECT id, page_number, source_kind, status, width, height,"
                " original_filename FROM pages ORDER BY page_number ASC"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise AppError(
            422,
            "backup_database_invalid",
            "The project database in the backup cannot be read.",
        ) from exc
    return [
        {
            "id": row["id"],
            "page_number": row["page_number"],
            "source_kind": row["source_kind"],
            "status": row["status"],
            "width": row["width"],
            "height": row["height"],
            "original_filename": row["original_filename"],
        }
        for row in rows
    ]


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
    archive_path: Path, *, project_id: str, source_name: str
) -> dict[str, Any]:
    """Extract and validate an archive, then list its pages for selection."""
    extracted = project_backup.extract_validated(archive_path)
    staging = extracted.directory
    try:
        pages = _list_pages(staging / "project.db")
        if not pages:
            raise AppError(
                422,
                "backup_no_pages",
                "This backup contains no pages to restore.",
            )
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
    if not isinstance(pages, list) or not pages:
        raise _expired()
    return Selection(
        token=token,
        directory=directory,
        source_name=str(payload.get("source_name") or "backup"),
        created_at=str(payload.get("created_at") or ""),
        pages=pages,
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
