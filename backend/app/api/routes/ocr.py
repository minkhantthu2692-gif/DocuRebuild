from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from app.api.deps import DbSession, ProjectDep
from app.schemas.ocr import (
    OcrBlockUpdate,
    OcrCapabilitiesOut,
    OcrRunOut,
    OcrRunRequest,
)
from app.services import ocr as ocr_service
from app.services import projects as project_service
from app.services.projects import touch_project

router = APIRouter(tags=["ocr"])


@router.get("/ocr/capabilities", response_model=OcrCapabilitiesOut)
def read_ocr_capabilities(refresh: bool = False) -> dict[str, Any]:
    return ocr_service.detect_engine(force=refresh)


@router.get(
    "/projects/{project_id}/pages/{page_id}/ocr",
    response_model=OcrRunOut | None,
)
def read_latest_ocr(project: ProjectDep, page_id: str) -> dict[str, Any] | None:
    directory = project_service.ensure_project_storage(project)
    return ocr_service.get_latest_ocr(directory, page_id)


@router.post(
    "/projects/{project_id}/pages/{page_id}/ocr",
    response_model=OcrRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_page_ocr(
    project: ProjectDep,
    page_id: str,
    payload: OcrRunRequest,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    run = ocr_service.start_ocr(directory, page_id, payload.languages)
    touch_project(session, project)
    return run


@router.get("/projects/{project_id}/ocr/runs/{run_id}", response_model=OcrRunOut)
def read_ocr_run(project: ProjectDep, run_id: str) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return ocr_service.get_run(directory, run_id)


@router.patch(
    "/projects/{project_id}/pages/{page_id}/ocr/blocks/{block_id}",
    response_model=OcrRunOut,
)
def update_ocr_block(
    project: ProjectDep,
    page_id: str,
    block_id: str,
    payload: OcrBlockUpdate,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    run = ocr_service.update_block(
        directory,
        page_id,
        block_id,
        text=payload.text,
        verified=payload.verified,
    )
    touch_project(session, project)
    return run
