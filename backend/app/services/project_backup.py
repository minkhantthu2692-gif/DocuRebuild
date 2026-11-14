"""Local project backup and restore.

A backup is a single zip archive of a project folder: its manifest, a
transaction-consistent snapshot of ``project.db``, the imported source and
processed images, thumbnails and exported files. The archive is written on this
device and is never uploaded anywhere.

Restoring is deliberately additive: a backup is always restored as a **new**
project with a new id, so an existing project is never overwritten. This makes a
restore reversible and keeps a damaged archive from destroying current work.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Project, utcnow
from app.db.project_schema import PROJECT_MIGRATIONS, project_db
from app.services import backup_crypto
from app.services import projects as project_service
from app.services.documents import ensure_document_row

BACKUP_VERSION = 1
# Only these paths may appear in an archive. Everything else (including a nested
# backups/ folder) is rejected, so a crafted archive cannot write arbitrary
# files into the project directory.
BACKUP_DIRS = ("source", "processed", "thumbnails", "exports")
ALLOWED_ROOTS = frozenset(("manifest.json", "backup.json", "project.db", *BACKUP_DIRS))
REQUIRED_ENTRIES = frozenset(("manifest.json", "backup.json", "project.db"))
UNSAFE_FILENAME = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')
ASCII_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
MAX_NAME_LENGTH = 160
MAX_DESCRIPTION_LENGTH = 2000
MAX_MIGRATION_VERSION = max(version for version, _ in PROJECT_MIGRATIONS)


@dataclass(frozen=True)
class RestoreCandidate:
    """An extracted, validated backup that is not registered yet."""

    directory: Path
    name: str
    description: str
    created_at: datetime
    original_project_id: str
    file_count: int


def _clean_stem(name: str, *, ascii_only: bool) -> str:
    cleaned = (ASCII_FILENAME if ascii_only else UNSAFE_FILENAME).sub("-", name.strip())
    cleaned = cleaned.strip(" .-_")[:80].strip(" .-_")
    return cleaned or "project"


def backup_filenames(project_name: str, *, encrypted: bool = False) -> tuple[str, str]:
    """Unicode-preserving and portable ASCII names for the download."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = backup_crypto.ENCRYPTED_SUFFIX if encrypted else ".zip"
    return (
        f"{_clean_stem(project_name, ascii_only=False)}-{stamp}{suffix}",
        f"{_clean_stem(project_name, ascii_only=True)}-{stamp}{suffix}",
    )


def _snapshot_database(directory: Path, target: Path) -> None:
    """Copy the project database through SQLite's backup API.

    A plain file copy could capture a database in the middle of a write (or miss
    rows still in the WAL file). The backup API produces a consistent snapshot
    even while another local request is saving.
    """
    source_path = directory / "project.db"
    if not source_path.is_file():
        raise AppError(
            409,
            "project_storage_incomplete",
            "The project database is missing, so it cannot be backed up.",
        )
    source = sqlite3.connect(source_path, timeout=15)
    target_connection = sqlite3.connect(target, timeout=15)
    try:
        source.backup(target_connection)
    finally:
        target_connection.close()
        source.close()


def _active_imports(directory: Path) -> bool:
    try:
        with project_db(directory) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM jobs"
                " WHERE status IN ('queued', 'running', 'cancelling')"
            ).fetchone()
        return bool(row and row["count"])
    except Exception:
        # A backup is still possible if the job table cannot be read.
        return False


def _missing_assets(database_path: Path, archive_names: set[str]) -> list[str]:
    """Assets referenced by the snapshot that the archive did not capture.

    Files are written before their database rows, so a snapshot taken while a
    page edit or import is finishing can reference a file that appeared after
    the folder scan. Reporting that is safer than producing a silently
    incomplete backup.
    """
    connection = sqlite3.connect(database_path, timeout=15)
    try:
        rows = connection.execute("SELECT relative_path FROM assets").fetchall()
    finally:
        connection.close()
    stored = {str(row[0]).replace("\\", "/") for row in rows if row[0]}
    return sorted(path for path in stored if path not in archive_names)


def create_backup(
    project: Project, *, password: str | None = None
) -> tuple[Path, str, str, int]:
    """Write a verified archive and return (path, Unicode name, ASCII name, size).

    When ``password`` is given the zip is wrapped in the encrypted container and
    the returned path is that container; the plaintext zip is removed first. The
    password is only used for this call and is never stored.
    """
    settings = get_settings()
    if password is not None:
        # Fail before writing an archive that could not be encrypted.
        backup_crypto.validate_password(password)
    directory = Path(project.directory)
    manifest_path = directory / "manifest.json"
    if not directory.is_dir() or not manifest_path.is_file():
        raise AppError(
            409,
            "project_storage_incomplete",
            "The project folder or manifest is missing, so it cannot be backed up.",
        )
    if _active_imports(directory):
        raise AppError(
            409,
            "backup_import_running",
            "Wait for the running import to finish before creating a backup.",
        )

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(settings.tmp_dir), suffix=".zip")
    os.close(handle)
    archive_path = Path(temp_name)
    database_copy = archive_path.with_suffix(".db")

    try:
        _snapshot_database(directory, database_copy)

        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.write(manifest_path, "manifest.json")
            archive.write(database_copy, "project.db")
            for folder in BACKUP_DIRS:
                root = directory / folder
                if not root.is_dir():
                    continue
                for path in sorted(root.rglob("*")):
                    if not path.is_file() or path.is_symlink():
                        continue
                    archive.write(path, f"{folder}/{path.relative_to(root).as_posix()}")
            archive.writestr(
                "backup.json",
                json.dumps(
                    {
                        "backup_version": BACKUP_VERSION,
                        "project_id": project.id,
                        "project_name": project.name,
                        "created_at": utcnow().isoformat(),
                        "app_version": settings.version,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

        # Re-open the finished archive so a truncated or corrupt write is caught
        # before the browser is told the backup succeeded.
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            missing = _missing_assets(database_copy, names)
            broken = archive.testzip()
        if missing:
            raise AppError(
                409,
                "backup_incomplete",
                "Project files changed while the backup was written. Try again.",
            )
        if broken is not None or not REQUIRED_ENTRIES.issubset(names):
            raise AppError(
                500,
                "backup_verification_failed",
                "The backup archive could not be verified.",
            )

        if password is not None:
            encrypted_path = archive_path.with_suffix(backup_crypto.ENCRYPTED_SUFFIX)
            backup_crypto.encrypt_file(archive_path, encrypted_path, password)
            archive_path.unlink(missing_ok=True)
            archive_path = encrypted_path
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    finally:
        database_copy.unlink(missing_ok=True)

    encrypted = password is not None
    unicode_name, ascii_name = backup_filenames(project.name, encrypted=encrypted)
    size = archive_path.stat().st_size
    project_service.record_history(
        directory,
        "project_backup_created",
        "Project backup created",
        {"filename": unicode_name, "byte_size": size, "encrypted": encrypted},
    )
    return archive_path, unicode_name, ascii_name, size


def _unsafe_name(name: str) -> bool:
    if not name or "\\" in name or "\x00" in name:
        return True
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        return True
    if any(":" in part for part in pure.parts):
        return True
    return pure.parts[0] not in ALLOWED_ROOTS


def _validate_archive(archive: zipfile.ZipFile) -> int:
    """Reject unsafe members and archive bombs before extracting anything."""
    settings = get_settings()
    limit = settings.max_backup_mb * 1024 * 1024
    total = 0
    files = 0
    for info in archive.infolist():
        if _unsafe_name(info.filename):
            raise AppError(
                422,
                "backup_unsafe_path",
                "The backup contains an unsupported or unsafe path.",
            )
        mode = info.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise AppError(
                422,
                "backup_unsafe_path",
                "The backup contains a symbolic link.",
            )
        if info.is_dir():
            continue
        total += info.file_size
        files += 1
        if total > limit:
            raise AppError(
                413,
                "backup_too_large",
                "The backup is larger than the configured limit when expanded.",
            )
    return files


def _extract_archive(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for info in archive.infolist():
        if info.is_dir():
            continue
        relative = PurePosixPath(info.filename)
        target = (destination / Path(*relative.parts)).resolve()
        if root not in target.parents:
            raise AppError(
                422,
                "backup_unsafe_path",
                "The backup contains an unsupported or unsafe path.",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AppError(
            422, "backup_invalid", "The backup metadata could not be read."
        ) from exc
    if not isinstance(value, dict):
        raise AppError(422, "backup_invalid", "The backup metadata is invalid.")
    return value


def _validate_database(path: Path) -> None:
    try:
        connection = sqlite3.connect(path, timeout=15)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            versions = [
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            ]
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise AppError(
            422,
            "backup_database_invalid",
            "The project database in the backup cannot be opened.",
        ) from exc

    if not integrity or integrity[0] != "ok":
        raise AppError(
            422,
            "backup_database_invalid",
            "The project database in the backup failed its integrity check.",
        )
    required_tables = {"documents", "pages", "assets", "schema_migrations"}
    if not required_tables.issubset(tables):
        raise AppError(
            422,
            "backup_database_invalid",
            "The project database in the backup is missing required data.",
        )
    if versions and max(versions) > MAX_MIGRATION_VERSION:
        raise AppError(
            422,
            "backup_incompatible",
            "The backup was created by a newer version of DocuRebuild.",
        )


def _parse_created_at(value: Any) -> datetime:
    if not isinstance(value, str):
        return utcnow()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return utcnow()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def prepare_restore(archive_path: Path) -> RestoreCandidate:
    """Validate an uploaded archive and extract it into a staging folder."""
    settings = get_settings()
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=str(settings.tmp_dir), prefix="restore-"))

    try:
        try:
            archive = zipfile.ZipFile(archive_path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise AppError(
                422, "backup_invalid", "The backup file is not a valid zip archive."
            ) from exc

        with archive:
            names = set(archive.namelist())
            missing = sorted(REQUIRED_ENTRIES - names)
            if missing:
                raise AppError(
                    422,
                    "backup_missing_files",
                    "The backup is missing required files.",
                )
            file_count = _validate_archive(archive)
            if archive.testzip() is not None:
                raise AppError(
                    422, "backup_invalid", "The backup archive is damaged."
                )
            _extract_archive(archive, staging)

        manifest = _read_json(staging / "manifest.json")
        metadata = _read_json(staging / "backup.json")
        if manifest.get("schema_version") != 1:
            raise AppError(
                422,
                "backup_incompatible",
                "The backup uses an unsupported project format.",
            )
        if metadata.get("backup_version") != BACKUP_VERSION:
            raise AppError(
                422,
                "backup_incompatible",
                "The backup uses an unsupported backup format.",
            )
        name = manifest.get("name")
        if not isinstance(name, str) or not name.strip():
            raise AppError(422, "backup_invalid", "The backup has no project name.")
        description = manifest.get("description")
        if not isinstance(description, str):
            description = ""
        _validate_database(staging / "project.db")

        candidate = RestoreCandidate(
            directory=staging,
            name=" ".join(name.split())[:MAX_NAME_LENGTH],
            description=description.strip()[:MAX_DESCRIPTION_LENGTH],
            created_at=_parse_created_at(manifest.get("created_at")),
            original_project_id=str(
                metadata.get("project_id") or manifest.get("project_id") or ""
            ),
            file_count=file_count,
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    # Internal provenance; the restored project keeps its history instead.
    (staging / "backup.json").unlink(missing_ok=True)
    return candidate


def _unique_name(session: Session, base: str) -> str:
    existing = {
        name.casefold() for name in session.scalars(select(Project.name)).all()
    }
    if base.casefold() not in existing:
        return base
    stem = f"{base} (restored)"[:MAX_NAME_LENGTH]
    candidate = stem
    counter = 2
    while candidate.casefold() in existing:
        suffix = f" {counter}"
        candidate = f"{stem[: MAX_NAME_LENGTH - len(suffix)].rstrip()}{suffix}"
        counter += 1
    return candidate


def finalize_restore(session: Session, candidate: RestoreCandidate) -> Project:
    """Register a validated candidate as a new project, without touching others."""
    settings = get_settings()
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    project_id = str(uuid.uuid4())
    target = (settings.projects_dir / project_id).resolve()
    name = _unique_name(session, candidate.name)

    try:
        candidate.directory.replace(target)
    except OSError:
        try:
            shutil.move(str(candidate.directory), str(target))
        except OSError as exc:
            shutil.rmtree(candidate.directory, ignore_errors=True)
            raise AppError(
                500,
                "backup_restore_failed",
                "The backup could not be moved into the projects folder.",
            ) from exc

    try:
        for folder in project_service.PROJECT_SUBDIRS:
            (target / folder).mkdir(parents=True, exist_ok=True)
        project = Project(
            id=project_id,
            name=name,
            description=candidate.description,
            directory=str(target),
            created_at=candidate.created_at,
            updated_at=utcnow(),
            last_opened_at=utcnow(),
        )
        project_service.write_manifest(project)
        with project_db(target) as conn:
            ensure_document_row(conn)
        project_service.record_history(
            target,
            "project_restored",
            "Project restored from backup",
            {"original_project_id": candidate.original_project_id},
        )
        session.add(project)
        session.commit()
        session.refresh(project)
    except Exception:
        session.rollback()
        shutil.rmtree(target, ignore_errors=True)
        raise
    return project
