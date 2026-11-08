from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import atomic_write_json
from app.db.models import Project, utcnow
from app.db.project_schema import project_db, utc_iso
from app.schemas.projects import ProjectCreate, ProjectUpdate, ProjectSummary
from app.services.documents import document_updated_at, ensure_document_row

logger = logging.getLogger(__name__)

PROJECT_SUBDIRS = ("source", "processed", "thumbnails", "exports", "backups", "trash")


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _write_manifest(project: Project) -> None:
    atomic_write_json(
        Path(project.directory) / "manifest.json",
        {
            "schema_version": 1,
            "project_id": project.id,
            "name": project.name,
            "description": project.description,
            "created_at": _utc_iso(project.created_at),
            "app_version": get_settings().version,
        },
    )


def ensure_project_storage(project: Project) -> Path:
    directory = Path(project.directory)
    if not directory.exists():
        raise AppError(
            409,
            "project_storage_missing",
            "The project folder is missing. Restore it from a backup or remove the project.",
        )
    for subdir in PROJECT_SUBDIRS:
        (directory / subdir).mkdir(parents=True, exist_ok=True)
    return directory


def page_count(directory: str | Path) -> int:
    try:
        with project_db(Path(directory)) as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM pages").fetchone()
        return int(row["count"])
    except Exception:
        logger.debug("Could not read page count for %s", directory, exc_info=True)
        return 0


def to_summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        description=project.description,
        page_count=page_count(project.directory),
        created_at=project.created_at,
        updated_at=project.updated_at,
        last_opened_at=project.last_opened_at,
    )


def list_projects(session: Session) -> list[Project]:
    from sqlalchemy import select

    return list(
        session.scalars(
            select(Project).order_by(
                Project.last_opened_at.desc().nulls_last(),
                Project.updated_at.desc(),
            )
        )
    )


def _parse_project_id(project_id: str) -> str:
    try:
        return str(UUID(project_id))
    except ValueError as exc:
        raise AppError(404, "project_not_found", "Project not found.") from exc


def get_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, _parse_project_id(project_id))
    if project is None:
        raise AppError(404, "project_not_found", "Project not found.")
    return project


def create_project(session: Session, payload: ProjectCreate) -> Project:
    settings = get_settings()
    project_id = str(uuid.uuid4())
    directory = (settings.projects_dir / project_id).resolve()
    project = Project(
        id=project_id,
        name=payload.name,
        description=payload.description.strip(),
        directory=str(directory),
    )

    try:
        directory.mkdir(parents=True, exist_ok=False)
        for subdir in PROJECT_SUBDIRS:
            (directory / subdir).mkdir(parents=True, exist_ok=True)
        _write_manifest(project)
        with project_db(directory) as conn:
            ensure_document_row(conn)
            conn.execute(
                "INSERT INTO history_events (id, event_type, summary, payload, created_at)"
                " VALUES (?, 'project_created', ?, '{}', ?)",
                (str(uuid.uuid4()), "Project created", utc_iso()),
            )
        session.add(project)
        session.commit()
        session.refresh(project)
    except Exception:
        session.rollback()
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        raise
    return project


def update_project(
    session: Session, project: Project, payload: ProjectUpdate
) -> Project:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in changes:
        project.name = changes["name"]
    if "description" in changes:
        project.description = changes["description"].strip()
    project.updated_at = utcnow()
    session.commit()
    session.refresh(project)
    try:
        _write_manifest(project)
    except OSError:
        logger.warning("Could not update project manifest for %s", project.id, exc_info=True)
    return project


def mark_opened(session: Session, project: Project) -> Project:
    project.last_opened_at = utcnow()
    session.commit()
    session.refresh(project)
    return project


def touch_project(session: Session, project: Project) -> None:
    project.updated_at = utcnow()
    session.commit()


def delete_project(session: Session, project: Project) -> str:
    settings = get_settings()
    directory = Path(project.directory)
    trash_path: Path | None = None
    if directory.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        trash_path = settings.trash_dir / f"{project.id}-{stamp}"
        counter = 1
        while trash_path.exists():
            trash_path = settings.trash_dir / f"{project.id}-{stamp}-{counter}"
            counter += 1
        settings.trash_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(directory), str(trash_path))
    session.delete(project)
    session.commit()
    return str(trash_path) if trash_path else ""


def project_detail_payload(project: Project) -> dict:
    summary = to_summary(project)
    payload = summary.model_dump()
    payload["directory"] = project.directory
    payload["document_updated_at"] = document_updated_at(Path(project.directory))
    return payload


def record_history(directory: str | Path, event_type: str, summary: str, payload: dict | None = None) -> None:
    try:
        with project_db(Path(directory)) as conn:
            conn.execute(
                "INSERT INTO history_events (id, event_type, summary, payload, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    event_type,
                    summary,
                    json.dumps(payload or {}, ensure_ascii=False),
                    utc_iso(),
                ),
            )
    except Exception:
        logger.warning("Could not record history event %s", event_type, exc_info=True)
