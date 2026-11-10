from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from app.api.deps import DbSession, ProjectDep
from app.schemas.elements import (
    ElementCreate,
    ElementOut,
    ElementTextRequest,
    ElementTextUpdate,
    ElementUpdate,
)
from app.services import elements as element_service
from app.services import projects as project_service
from app.services.projects import touch_project

router = APIRouter(tags=["elements"])


@router.get(
    "/projects/{project_id}/pages/{page_id}/elements",
    response_model=list[ElementOut],
)
def list_elements(project: ProjectDep, page_id: str) -> list[dict[str, Any]]:
    directory = project_service.ensure_project_storage(project)
    return element_service.list_elements(directory, page_id)


@router.post(
    "/projects/{project_id}/pages/{page_id}/elements",
    response_model=ElementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_element(
    project: ProjectDep,
    page_id: str,
    payload: ElementCreate,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    element = element_service.create_element(
        directory,
        page_id,
        kind=payload.kind,
        x=payload.x,
        y=payload.y,
        width=payload.width,
        height=payload.height,
        caption=payload.caption,
    )
    touch_project(session, project)
    return element


@router.patch(
    "/projects/{project_id}/elements/{element_id}",
    response_model=ElementOut,
)
def update_element(
    project: ProjectDep,
    element_id: str,
    payload: ElementUpdate,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    element = element_service.update_element(
        directory,
        element_id,
        caption=payload.caption,
        verified=payload.verified,
    )
    touch_project(session, project)
    return element


@router.post(
    "/projects/{project_id}/elements/{element_id}/text",
    response_model=ElementOut,
)
def extract_element_text(
    project: ProjectDep,
    element_id: str,
    payload: ElementTextRequest,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    element = element_service.extract_element_text(
        directory, element_id, payload.languages
    )
    touch_project(session, project)
    return element


@router.patch(
    "/projects/{project_id}/elements/{element_id}/text",
    response_model=ElementOut,
)
def update_element_text(
    project: ProjectDep,
    element_id: str,
    payload: ElementTextUpdate,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    element = element_service.update_element_text(directory, element_id, payload.text)
    touch_project(session, project)
    return element


@router.delete("/projects/{project_id}/elements/{element_id}")
def delete_element(
    project: ProjectDep, element_id: str, session: DbSession
) -> dict[str, bool]:
    directory = project_service.ensure_project_storage(project)
    element_service.delete_element(directory, element_id)
    touch_project(session, project)
    return {"ok": True}
