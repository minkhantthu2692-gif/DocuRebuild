"""Factory reset for the local application data folder.

The reset is deliberately narrow: it removes only files and folders DocuRebuild
itself creates inside the configured data directory. A user who points
``DOCUREBUILD_DATA_DIR`` at a folder that also holds unrelated files keeps those
files. Nothing outside the data directory is touched, and the installed
application, its logs and its window preference stay in place.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import dispose_engine, run_migrations
from app.services import imports as import_service
from app.services import ocr as ocr_service

logger = logging.getLogger(__name__)

# Every entry this application owns at the top level of its data folder.
# Project folders, temporary previews and encrypted AI keys live inside these.
DATA_ENTRIES = (
    "projects",
    "trash",
    "tmp",
    "backups",
    "fonts",
    "secrets",
    "app.db",
    "app.db-wal",
    "app.db-shm",
)

# Windows can keep a directory handle briefly after a worker exits or after the
# SQLite pool is disposed. A short bounded retry avoids reporting a failure for
# a handle that is already being released.
REMOVE_ATTEMPTS = 6
RETRY_DELAY_SECONDS = 0.25


def _remove_entry(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _remove_with_retry(path: Path) -> None:
    last_error: OSError | None = None
    for attempt in range(REMOVE_ATTEMPTS):
        try:
            _remove_entry(path)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            last_error = exc
            if attempt < REMOVE_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
    assert last_error is not None
    raise last_error


def _guard_data_dir(data_dir: Path) -> None:
    """Refuse a reset that would target a drive root, the home folder or a file."""
    if data_dir.exists() and not data_dir.is_dir():
        raise AppError(
            500,
            "reset_data_dir_invalid",
            "The configured data folder is not a directory, so it was not reset.",
        )
    if data_dir == Path(data_dir.anchor) or data_dir == Path.home():
        raise AppError(
            500,
            "reset_unsafe_location",
            "The configured data folder is too broad to reset safely.",
        )


def _count_project_folders(projects_dir: Path) -> int:
    if not projects_dir.is_dir():
        return 0
    try:
        return sum(1 for child in projects_dir.iterdir() if child.is_dir())
    except OSError:
        return 0


def reset_application_data() -> dict[str, object]:
    """Erase local projects, database, settings, keys and backups.

    Background workers are stopped and the SQLAlchemy engine is disposed before
    any file is removed. The folder layout and an empty database are recreated
    before the response returns, so the next request sees a fresh installation.
    """
    settings = get_settings()
    data_dir = settings.data_dir.resolve()
    _guard_data_dir(data_dir)

    project_count = _count_project_folders(data_dir / "projects")

    # Stop writers first, then close every pooled app-database connection.
    import_service.shutdown_import_executor(wait=True)
    ocr_service.shutdown_ocr_executor(wait=True)
    ocr_service.clear_engine_cache()
    dispose_engine()

    failed: list[str] = []
    for name in DATA_ENTRIES:
        try:
            _remove_with_retry(data_dir / name)
        except OSError:
            logger.exception("Factory reset could not remove %s", name)
            failed.append(name)

    # Recreate the empty layout and schema even after a partial removal: leaving
    # a half-deleted database behind is worse than reporting the failure.
    settings.ensure_layout()
    dispose_engine()
    run_migrations()

    if failed:
        raise AppError(
            500,
            "reset_incomplete",
            "DocuRebuild could not remove every data file. Close other applications "
            "that may be using the data folder, then try again.",
        )

    logger.info("Factory reset removed %s project folder(s)", project_count)
    return {
        "ok": True,
        "data_dir": str(data_dir),
        "projects_removed": project_count,
    }
