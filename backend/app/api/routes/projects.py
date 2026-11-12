from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
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
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
)
from app.services import documents, projects as project_service
from app.services import imports as import_service
from app.services import pages as page_service
from app.services.document_export import ExportFormat, export_document, safe_filename
from app.services.projects import touch_project

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


@router.post("/{project_id}/open", response_model=ProjectDetail)
def open_project(project: ProjectDep, session: DbSession) -> dict[str, Any]:
    project_service.ensure_project_storage(project)
    opened = project_service.mark_opened(session, project)
    return _detail(opened)


@router.delete("/{project_id}")
def delete_project(project: ProjectDep, session: DbSession) -> dict[str, Any]:
    trash_path = project_service.delete_project(session, project)
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
    """Return the stored document as a UTF-8 attachment (Markdown or TXT)."""
    directory = project_service.ensure_project_storage(project)
    body, filename, content_type = export_document(directory, project.name, export_format)
    ascii_name = safe_filename(project.name, export_format)
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )
    return Response(
        content=body,
        media_type=content_type,
        headers={"Content-Disposition": disposition},
    )


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
