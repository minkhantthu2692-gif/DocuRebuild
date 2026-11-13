from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.deps import DbSession, ProjectDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.imports import ImportJobOut
from app.schemas.pages import (
    DeskewEstimate,
    EditsRequest,
    PageOut,
    ReorderRequest,
    RotateRequest,
)
from app.schemas.projects import (
    DocumentOut,
    DocumentPayload,
    DocumentRevisionOut,
    DocumentRevisionSummary,
    HistoryEventOut,
    ProjectBackupSummary,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
)
from app.services import documents, projects as project_service
from app.services import history as history_service
from app.services import imports as import_service
from app.services import local_backups
from app.services import pages as page_service
from app.services import project_backup
from app.services.document_export import ExportFormat, export_document, safe_filename
from app.services.projects import touch_project
from app.services.settings import get_app_settings

router = APIRouter(prefix="/projects", tags=["projects"])


def _detail(project) -> dict[str, Any]:
    return project_service.project_detail_payload(project)


@router.get("", response_model=list[ProjectSummary])
def list_projects(session: DbSession) -> list[ProjectSummary]:
    return [project_service.to_summary(item) for item in project_service.list_projects(session)]


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: DbSession) -> dict[str, Any]:
    project = project_service.create_project(session, payload)
    return _detail(project)


@router.get("/{project_id}", response_model=ProjectDetail)
def read_project(project: ProjectDep) -> dict[str, Any]:
    return _detail(project)


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(
    project: ProjectDep, payload: ProjectUpdate, session: DbSession
) -> dict[str, Any]:
    updated = project_service.update_project(session, project, payload)
    return _detail(updated)


@router.get("/{project_id}/backup")
def download_project_backup(project: ProjectDep) -> FileResponse:
    """Build and download a verified local backup of the whole project."""
    path, unicode_name, ascii_name, _size = project_backup.create_backup(project)
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(unicode_name, safe='')}"
    )
    return FileResponse(
        path,
        media_type="application/zip",
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "private, no-store",
        },
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@router.get("/{project_id}/backups", response_model=list[ProjectBackupSummary])
def list_local_backups(project: ProjectDep) -> list[dict[str, Any]]:
    """List the local backup copies kept for this project, newest first."""
    return local_backups.list_copies(project.id)


@router.post(
    "/{project_id}/backups",
    response_model=ProjectBackupSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_local_backup(project: ProjectDep, session: DbSession) -> dict[str, Any]:
    """Write one verified backup copy into the local vault."""
    keep = get_app_settings(session).backups.keep_copies
    return local_backups.create_copy(project, keep=keep)


@router.get("/{project_id}/backups/{filename}")
def download_local_backup(project: ProjectDep, filename: str) -> FileResponse:
    """Download a stored copy without removing it from the vault."""
    path = local_backups.resolve_copy(project.id, filename)
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip(" .-_") or "backup.zip"
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )
    return FileResponse(
        path,
        media_type="application/zip",
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{project_id}/backups/{filename}")
def delete_local_backup(project: ProjectDep, filename: str) -> dict[str, Any]:
    """Delete one stored copy that the user explicitly selected."""
    return local_backups.delete_copy(project.id, filename)


@router.post(
    "/{project_id}/backups/{filename}/restore",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
)
def restore_local_backup(
    project: ProjectDep, filename: str, session: DbSession
) -> dict[str, Any]:
    """Restore a stored copy as a new project. Nothing is overwritten."""
    restored = local_backups.restore_copy(session, project, filename)
    return _detail(restored)


@router.post(
    "/restore",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
)
async def restore_project_backup(
    session: DbSession,
    file: Annotated[UploadFile, File(description="DocuRebuild backup archive")],
) -> dict[str, Any]:
    """Restore a backup as a new project. No existing project is overwritten."""
    settings = get_settings()
    if Path(file.filename or "").suffix.lower() != ".zip":
        raise AppError(422, "backup_invalid", "Choose a .zip backup file.")

    temp_dir = settings.tmp_dir
    temp_dir.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(temp_dir), suffix=".zip")
    temp_path = Path(temp_name)
    limit = settings.max_backup_mb * 1024 * 1024
    size = 0
    try:
        with os.fdopen(handle, "wb") as target:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise AppError(
                        413,
                        "backup_too_large",
                        f"Backups are limited to {settings.max_backup_mb} MB.",
                    )
                target.write(chunk)
        if size == 0:
            raise AppError(422, "backup_invalid", "The backup file is empty.")

        candidate = await run_in_threadpool(
            project_backup.prepare_restore, temp_path
        )
        try:
            project = project_backup.finalize_restore(session, candidate)
        except Exception:
            shutil.rmtree(candidate.directory, ignore_errors=True)
            raise
    finally:
        temp_path.unlink(missing_ok=True)
    return _detail(project)


@router.post("/{project_id}/open", response_model=ProjectDetail)
def open_project(
    project: ProjectDep, session: DbSession, background: BackgroundTasks
) -> dict[str, Any]:
    project_service.ensure_project_storage(project)
    opened = project_service.mark_opened(session, project)
    # Opt-in only: the copy runs after the response so opening never waits for
    # an archive, and the background task re-reads the settings in its own session.
    if get_app_settings(session).backups.auto_on_open:
        background.add_task(local_backups.auto_copy_for_project, project.id)
    return _detail(opened)


@router.delete("/{project_id}")
def delete_project(project: ProjectDep, session: DbSession) -> dict[str, Any]:
    trash_path = project_service.delete_project(session, project)
    base_name = Path(trash_path).name if trash_path else None
    local_backups.trash_project_vault(project.id, base_name)
    return {"ok": True, "trash_path": trash_path}


# --------------------------------------------------------------------------- #
# Document
# --------------------------------------------------------------------------- #


@router.get("/{project_id}/document", response_model=DocumentOut)
def read_document(project: ProjectDep) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return documents.read_document(directory)


@router.put("/{project_id}/document", response_model=DocumentOut)
def write_document(
    project: ProjectDep, payload: DocumentPayload, session: DbSession
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    document = documents.write_document(directory, payload.content, payload.plain_text)
    touch_project(session, project)
    return document


@router.get("/{project_id}/document/export")
def export_document_file(
    project: ProjectDep,
    export_format: Annotated[ExportFormat, Query(alias="format")] = "markdown",
) -> Response:
    """Return the stored document as an attachment (Markdown, TXT or DOCX)."""
    directory = project_service.ensure_project_storage(project)
    body, filename, content_type = export_document(directory, project.name, export_format)
    ascii_name = safe_filename(project.name, export_format)
    project_service.record_history(
        directory,
        "document_exported",
        f"Exported {export_format}",
        {"format": export_format, "byte_size": len(body)},
    )
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )
    return Response(
        content=body,
        media_type=content_type,
        headers={"Content-Disposition": disposition},
    )


@router.get(
    "/{project_id}/document/revisions",
    response_model=list[DocumentRevisionSummary],
)
def list_document_revisions(
    project: ProjectDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    directory = project_service.ensure_project_storage(project)
    return documents.list_revisions(directory, limit)


@router.post(
    "/{project_id}/document/revisions",
    response_model=DocumentRevisionSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_document_revision(
    project: ProjectDep, session: DbSession
) -> dict[str, Any]:
    """Checkpoint the current saved document, so it can be restored later."""
    directory = project_service.ensure_project_storage(project)
    revision = documents.create_revision(directory)
    touch_project(session, project)
    return revision


@router.get(
    "/{project_id}/document/revisions/{revision_id}",
    response_model=DocumentRevisionOut,
)
def read_document_revision(
    project: ProjectDep, revision_id: str
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return documents.read_revision(directory, revision_id)


@router.post(
    "/{project_id}/document/revisions/{revision_id}/restore",
    response_model=DocumentOut,
)
def restore_document_revision(
    project: ProjectDep, revision_id: str, session: DbSession
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    document = documents.restore_revision(directory, revision_id)
    touch_project(session, project)
    return document


@router.get("/{project_id}/history", response_model=list[HistoryEventOut])
def read_project_history(
    project: ProjectDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    """Local activity log for this project, newest first."""
    directory = project_service.ensure_project_storage(project)
    return history_service.list_events(directory, limit)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #


@router.get("/{project_id}/pages", response_model=list[PageOut])
def list_pages(project: ProjectDep) -> list[dict[str, Any]]:
    directory = project_service.ensure_project_storage(project)
    return page_service.list_pages(directory)


async def _receive_uploads(
    files: list[UploadFile],
) -> list[tuple[str, Path]]:
    """Stream uploaded files to the local temp folder with limit checks."""
    settings = get_settings()
    if not files:
        raise AppError(400, "no_files", "No files were provided.")
    if len(files) > settings.max_upload_batch:
        raise AppError(
            400,
            "too_many_files",
            f"Import at most {settings.max_upload_batch} files at a time.",
        )

    temp_dir = settings.data_dir / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_import_mb * 1024 * 1024
    pending: list[tuple[str, Path]] = []
    try:
        for upload in files:
            filename = Path(upload.filename or "unnamed").name
            extension = page_service.validate_import_name(filename)
            handle, temp_name = tempfile.mkstemp(dir=str(temp_dir), suffix=extension)
            temp_path = Path(temp_name)
            pending.append((filename, temp_path))
            size = 0
            with os.fdopen(handle, "wb") as target:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise AppError(
                            413,
                            "file_too_large",
                            f"'{filename}' exceeds the {settings.max_import_mb} MB limit.",
                        )
                    target.write(chunk)
            if size == 0:
                raise AppError(422, "empty_file", f"'{filename}' is empty.")
        return pending
    except Exception:
        page_service.discard_temporary_uploads(pending)
        raise


@router.post("/{project_id}/pages/import", response_model=list[PageOut])
async def import_pages(
    project: ProjectDep,
    session: DbSession,
    files: Annotated[list[UploadFile], File(description="Image files to import")],
) -> list[dict[str, Any]]:
    """Synchronous import kept for simple clients; the workspace uses jobs."""
    directory = project_service.ensure_project_storage(project)
    pending = await _receive_uploads(files)
    try:
        rows = await run_in_threadpool(page_service.import_files, directory, pending)
        touch_project(session, project)
        return sorted(rows, key=lambda row: row["page_number"])
    finally:
        for _, temp_path in pending:
            temp_path.unlink(missing_ok=True)


@router.post(
    "/{project_id}/imports",
    response_model=ImportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_import_job(
    project: ProjectDep,
    session: DbSession,
    files: Annotated[list[UploadFile], File(description="Image or PDF files to import")],
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    pending = await _receive_uploads(files)
    try:
        inspected = await run_in_threadpool(page_service.inspect_uploads, pending)
    except Exception:
        page_service.discard_temporary_uploads(pending)
        raise

    job = import_service.create_import_job(directory, pending, inspected)
    touch_project(session, project)
    return job


@router.get("/{project_id}/imports", response_model=list[ImportJobOut])
def list_import_jobs(project: ProjectDep, limit: int = 10) -> list[dict[str, Any]]:
    directory = project_service.ensure_project_storage(project)
    return import_service.list_import_jobs(directory, limit=limit)


@router.get("/{project_id}/imports/{job_id}", response_model=ImportJobOut)
def read_import_job(project: ProjectDep, job_id: str) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return import_service.get_import_job(directory, job_id)


@router.post("/{project_id}/imports/{job_id}/cancel", response_model=ImportJobOut)
def cancel_import_job(project: ProjectDep, job_id: str) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return import_service.cancel_import_job(directory, job_id)


@router.post("/{project_id}/pages/{page_id}/rotate", response_model=PageOut)
def rotate_page(
    project: ProjectDep, page_id: str, payload: RotateRequest, session: DbSession
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    page = page_service.rotate_page(directory, page_id, payload.degrees)
    touch_project(session, project)
    return page


@router.delete("/{project_id}/pages/{page_id}")
def delete_page(project: ProjectDep, page_id: str, session: DbSession) -> dict[str, bool]:
    directory = project_service.ensure_project_storage(project)
    page_service.delete_page(directory, page_id)
    touch_project(session, project)
    return {"ok": True}


@router.patch("/{project_id}/pages/{page_id}/edits", response_model=PageOut)
def update_page_edits(
    project: ProjectDep, page_id: str, payload: EditsRequest, session: DbSession
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    page = page_service.update_page_edits(directory, page_id, payload.edits)
    touch_project(session, project)
    return page


@router.post("/{project_id}/pages/{page_id}/edits/reset", response_model=PageOut)
def reset_page_edits(
    project: ProjectDep, page_id: str, session: DbSession
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    page = page_service.reset_page_edits(directory, page_id)
    touch_project(session, project)
    return page


@router.get("/{project_id}/pages/{page_id}/edits/base")
def page_base_preview(project: ProjectDep, page_id: str) -> FileResponse:
    directory = project_service.ensure_project_storage(project)
    path = page_service.base_page_preview(directory, page_id)
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=0, must-revalidate"},
    )


@router.get("/{project_id}/pages/{page_id}/deskew-estimate", response_model=DeskewEstimate)
def estimate_page_skew(project: ProjectDep, page_id: str) -> DeskewEstimate:
    directory = project_service.ensure_project_storage(project)
    return DeskewEstimate(angle=page_service.estimate_page_skew(directory, page_id))


@router.put("/{project_id}/pages/order", response_model=list[PageOut])
def reorder_pages(
    project: ProjectDep, payload: ReorderRequest, session: DbSession
) -> list[dict[str, Any]]:
    directory = project_service.ensure_project_storage(project)
    rows = page_service.reorder_pages(directory, payload.page_ids)
    touch_project(session, project)
    return rows


@router.get("/{project_id}/assets/{asset_id}/file")
def serve_asset(project: ProjectDep, asset_id: str) -> FileResponse:
    directory = project_service.ensure_project_storage(project)
    path, mime = page_service.get_asset_file(directory, asset_id)
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=0, must-revalidate"},
    )
