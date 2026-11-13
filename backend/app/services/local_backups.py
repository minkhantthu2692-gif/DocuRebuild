"""User-initiated local backup copies.

A download is a one-off file. This vault keeps recent verified project archives on
disk so a lost or damaged download is not the only recovery path. Copies are
created only when the user asks for one, live under the application data
directory, and are pruned to a small fixed count per project.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Project
from app.services import project_backup

logger = logging.getLogger(__name__)

# Small on purpose: archives contain every source asset, so an unbounded vault
# could fill the disk. The newest copies are kept.
KEEP_COPIES = 5


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
