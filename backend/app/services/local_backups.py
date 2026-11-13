"""Local backup copies.

A download is a one-off file. This vault keeps recent verified project archives on
disk so a lost or damaged download is not the only recovery path. Copies are
created when the user asks, or after opening a project when opted in, live under
the application data directory, are pruned to a configurable count per project,
and can be downloaded, restored as a new project, or deleted explicitly.
"""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Project
from app.db.session import get_session_factory
from app.services import project_backup
from app.services.settings import get_app_settings

logger = logging.getLogger(__name__)

# Default retention when no saved preference is supplied. The UI and settings
# can raise or lower it, but an unbounded vault could fill the disk.
KEEP_COPIES = 5

# Serializes automatic copies so two simultaneous opens cannot both decide that
# a copy is due and write the same snapshot twice.
_auto_lock = threading.Lock()


def vault_dir(project_id: str) -> Path:
    return get_settings().backups_dir / project_id


def _summary(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "filename": path.name,
        "byte_size": stat.st_size,
        "created_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        # Internal ordering key; not part of the API response.
        "_order": stat.st_mtime_ns,
    }


def list_copies(project_id: str) -> list[dict[str, object]]:
    folder = vault_dir(project_id)
    if not folder.is_dir():
        return []
    copies: list[dict[str, object]] = []
    for path in folder.iterdir():
        if path.suffix.lower() != ".zip" or path.is_symlink() or not path.is_file():
            continue
        try:
            copies.append(_summary(path))
        except OSError:
            # A file can disappear between iterating and reading its metadata.
            continue
    copies.sort(key=lambda item: (item["_order"], item["filename"]), reverse=True)
    for item in copies:
        item.pop("_order", None)
    return copies


def _unique_target(folder: Path, filename: str) -> Path:
    target = folder / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 2
    while True:
        candidate = folder / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def prune(project_id: str, keep: int | None = None) -> int:
    """Delete the oldest copies beyond ``keep`` and return the removed count."""
    if keep is None:
        keep = KEEP_COPIES
    removed = 0
    for entry in list_copies(project_id)[max(keep, 0):]:
        path = vault_dir(project_id) / str(entry["filename"])
        try:
            path.unlink()
            removed += 1
        except OSError:
            logger.warning("Could not remove old backup copy %s", path, exc_info=True)
    return removed


def create_copy(project: Project, keep: int | None = None) -> dict[str, object]:
    """Write a verified archive into the vault and prune old copies."""
    if keep is None:
        keep = KEEP_COPIES
    archive_path, _unicode_name, _ascii_name, _size = project_backup.create_backup(project)
    folder = vault_dir(project.id)
    folder.mkdir(parents=True, exist_ok=True)
    target = _unique_target(folder, _unicode_name)
    try:
        shutil.move(str(archive_path), target)
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    prune(project.id, keep)
    return {key: value for key, value in _summary(target).items() if key != "_order"}


def resolve_copy(project_id: str, filename: str) -> Path:
    """Return one stored archive, rejecting anything that is not a plain name."""
    if (
        not filename
        or filename != Path(filename).name
        or "\\" in filename
        or "/" in filename
        or Path(filename).suffix.lower() != ".zip"
    ):
        raise AppError(404, "backup_not_found", "That backup copy does not exist.")
    path = vault_dir(project_id) / filename
    if path.is_symlink() or not path.is_file():
        raise AppError(404, "backup_not_found", "That backup copy does not exist.")
    return path


def delete_copy(project_id: str, filename: str) -> dict[str, object]:
    """Remove one stored copy after the user explicitly asks for it."""
    path = resolve_copy(project_id, filename)
    try:
        path.unlink()
    except FileNotFoundError as exc:
        raise AppError(
            404, "backup_not_found", "That backup copy does not exist."
        ) from exc
    except OSError as exc:
        logger.warning("Could not delete backup copy %s", path, exc_info=True)
        raise AppError(
            500, "backup_delete_failed", "The backup copy could not be deleted."
        ) from exc
    return {"ok": True, "filename": filename}


def restore_copy(session: Session, project: Project, filename: str) -> Project:
    """Restore a stored copy as a new project.

    ``prepare_restore()`` only reads the archive, so the stored copy and the
    project it came from stay untouched. Restoring is additive by design: the
    result is a new project with a new id.
    """
    path = resolve_copy(project.id, filename)
    limit = get_settings().max_backup_mb * 1024 * 1024
    try:
        compressed = path.stat().st_size
    except OSError as exc:
        raise AppError(
            404, "backup_not_found", "That backup copy does not exist."
        ) from exc
    if compressed > limit:
        raise AppError(
            413,
            "backup_too_large",
            f"Backups are limited to {get_settings().max_backup_mb} MB.",
        )

    candidate = project_backup.prepare_restore(path)
    try:
        return project_backup.finalize_restore(session, candidate)
    except Exception:
        shutil.rmtree(candidate.directory, ignore_errors=True)
        raise


def trash_project_vault(project_id: str, base_name: str | None = None) -> Path | None:
    """Move a deleted project's vault folder into the local trash.

    The copies are preserved rather than destroyed, but they stop appearing under
    the deleted project id. A move failure is logged and never blocks deletion.
    """
    folder = vault_dir(project_id)
    if not folder.is_dir():
        return None
    settings = get_settings()
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = base_name or f"{project_id}-{stamp}"
    target = settings.trash_dir / f"{name}-vault"
    counter = 1
    while target.exists():
        target = settings.trash_dir / f"{name}-vault-{counter}"
        counter += 1
    try:
        shutil.move(str(folder), str(target))
    except OSError:
        logger.warning("Could not move vault for project %s to trash", project_id, exc_info=True)
        return None
    return target


def is_due(
    project_id: str,
    interval_hours: int,
    *,
    now: datetime | None = None,
) -> bool:
    """True when the vault has no copy or its newest copy is old enough."""
    copies = list_copies(project_id)
    if not copies:
        return True
    try:
        newest = datetime.fromisoformat(str(copies[0]["created_at"]))
    except ValueError:
        return True
    current = now or datetime.now(timezone.utc)
    return current - newest >= timedelta(hours=interval_hours)


def auto_copy(
    project: Project,
    interval_hours: int,
    keep: int,
) -> dict[str, object] | None:
    """Create one copy when due, serialized with other automatic copies."""
    with _auto_lock:
        if not is_due(project.id, interval_hours):
            return None
        return create_copy(project, keep=keep)


def auto_copy_for_project(project_id: str) -> None:
    """Background entry point: re-read preferences and copy only when opted in.

    Runs in a fresh session because the request session is already closed. A
    failure is logged and never affects the project that was just opened.
    """
    session = get_session_factory()()
    try:
        project = session.get(Project, project_id)
        if project is None:
            return
        prefs = get_app_settings(session).backups
        if not prefs.auto_on_open:
            return
        created = auto_copy(project, prefs.interval_hours, prefs.keep_copies)
        if created is not None:
            logger.info("Created automatic backup copy %s", created["filename"])
    except Exception:
        logger.warning("Automatic backup copy failed for project %s", project_id, exc_info=True)
    finally:
        session.close()
