from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, ProjectDep
from app.schemas.ai import (
    AiProbeOut,
    AiProbeRequest,
    AiProvidersOut,
    AiSuggestionCreate,
    AiSuggestionDecisionIn,
    AiSuggestionDecisionOut,
    AiSuggestionStatus,
    AiSuggestionsOut,
)
from app.services import ai as ai_service
from app.services import projects as project_service
from app.services.projects import touch_project
from app.services.settings import get_app_settings

router = APIRouter(tags=["ai"])


@router.get("/ai/providers", response_model=AiProvidersOut)
def list_ai_providers() -> dict[str, Any]:
    return {"providers": ai_service.provider_catalog()}


@router.post("/ai/probe", response_model=AiProbeOut)
def probe_ai_provider(payload: AiProbeRequest) -> dict[str, Any]:
    return ai_service.probe_provider(
        payload.provider,
        payload.base_url,
        allow_remote=payload.allow_remote,
    )


@router.get(
    "/projects/{project_id}/pages/{page_id}/ai-suggestions",
    response_model=AiSuggestionsOut,
)
def list_ai_suggestions(
    project: ProjectDep,
    page_id: str,
    suggestion_status: AiSuggestionStatus | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return {
        "suggestions": ai_service.list_page_suggestions(
            directory,
            page_id,
            suggestion_status,
        )
    }


@router.post(
    "/projects/{project_id}/pages/{page_id}/ocr/blocks/{block_id}/ai-suggestions",
    response_model=AiSuggestionDecisionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_cleanup_suggestion(
    project: ProjectDep,
    page_id: str,
    block_id: str,
    payload: AiSuggestionCreate,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    profile = get_app_settings(session).ai.text
    suggestion, run = ai_service.create_cleanup_suggestion(
        directory,
        page_id,
        block_id,
        profile,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
    )
    touch_project(session, project)
    return {"suggestion": suggestion, "run": run}


@router.patch(
    "/projects/{project_id}/ai-suggestions/{suggestion_id}",
    response_model=AiSuggestionDecisionOut,
)
def decide_ai_suggestion(
    project: ProjectDep,
    suggestion_id: str,
    payload: AiSuggestionDecisionIn,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    suggestion, run = ai_service.decide_suggestion(directory, suggestion_id, payload.status)
    touch_project(session, project)
    return {"suggestion": suggestion, "run": run}
