from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy.orm import Session

from app.api.deps import DbSession, ProjectDep
from app.core.errors import AppError
from app.schemas.ai import (
    AiProbeOut,
    AiProbeRequest,
    AiProvidersOut,
    AiRegionProposalsOut,
    AiRegionProposalsRequest,
    AiSuggestionCreate,
    AiSuggestionDecisionIn,
    AiSuggestionDecisionOut,
    AiSuggestionStatus,
    AiSuggestionsOut,
    AiUsageOut,
)
from app.services import ai as ai_service
from app.services import ai_usage
from app.services import ai_vision
from app.services import projects as project_service
from app.services.projects import touch_project
from app.services.settings import get_app_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai"])


def _commit_usage(session: Session) -> None:
    """Persist usage metadata without hiding the provider or validation error."""
    try:
        session.commit()
    except Exception:
        logger.exception("Could not persist local AI usage metadata.")
        session.rollback()


@router.get("/ai/providers", response_model=AiProvidersOut)
def list_ai_providers() -> dict[str, Any]:
    return {"providers": ai_service.provider_catalog()}


@router.get("/ai/usage", response_model=AiUsageOut)
def read_ai_usage(session: DbSession) -> dict[str, Any]:
    ai_settings = get_app_settings(session).ai
    return ai_usage.usage_summary(session, ai_settings.request_limit)


@router.post("/ai/probe", response_model=AiProbeOut)
def probe_ai_provider(payload: AiProbeRequest) -> dict[str, Any]:
    return ai_service.probe_provider(
        payload.provider,
        payload.base_url,
        allow_remote=payload.allow_remote,
    )


@router.post(
    "/projects/{project_id}/pages/{page_id}/ai-region-proposals",
    response_model=AiRegionProposalsOut,
)
def create_ai_region_proposals(
    project: ProjectDep,
    page_id: str,
    payload: AiRegionProposalsRequest,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    ai_settings = get_app_settings(session).ai
    if not ai_settings.vision_model:
        raise AppError(
            409,
            "ai_vision_not_configured",
            "Choose a vision model in Settings before analysing page images.",
        )
    ai_usage.ensure_within_limit(session, ai_settings.request_limit)

    def record_attempt(attempt: ai_service.RequestAttempt) -> None:
        ai_usage.record_attempt(
            session,
            provider=attempt.provider,
            model=attempt.model,
            task="region_proposals",
            outcome="error" if attempt.error_code else "success",
            error_code=attempt.error_code,
            project_id=project.id,
            page_id=page_id,
            block_id=None,
        )

    try:
        result = ai_vision.propose_regions(
            directory,
            page_id,
            ai_settings.text,
            ai_settings.vision_model,
            provider=payload.provider,
            base_url=payload.base_url,
            model=payload.model,
            on_attempt=record_attempt,
        )
    except Exception:
        _commit_usage(session)
        raise
    touch_project(session, project)
    return result


@router.get(
    "/projects/{project_id}/pages/{page_id}/ai-suggestions",
    response_model=AiSuggestionsOut,
)
def list_ai_suggestions(
    project: ProjectDep,
    page_id: str,
    suggestion_status: AiSuggestionStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return {
        "suggestions": ai_service.list_page_suggestions(
            directory,
            page_id,
            suggestion_status,
            limit,
        )
    }


@router.get(
    "/projects/{project_id}/ai-suggestions",
    response_model=AiSuggestionsOut,
)
def list_project_ai_suggestions(
    project: ProjectDep,
    suggestion_status: AiSuggestionStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return {
        "suggestions": ai_service.list_project_suggestions(
            directory,
            suggestion_status,
            limit,
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
    ai_settings = get_app_settings(session).ai
    ai_usage.ensure_within_limit(session, ai_settings.request_limit)

    def record_attempt(attempt: ai_service.RequestAttempt) -> None:
        ai_usage.record_attempt(
            session,
            provider=attempt.provider,
            model=attempt.model,
            task="ocr_cleanup",
            outcome="error" if attempt.error_code else "success",
            error_code=attempt.error_code,
            project_id=project.id,
            page_id=page_id,
            block_id=block_id,
        )

    try:
        suggestion, run = ai_service.create_cleanup_suggestion(
            directory,
            page_id,
            block_id,
            ai_settings.text,
            provider=payload.provider,
            base_url=payload.base_url,
            model=payload.model,
            on_attempt=record_attempt,
        )
    except Exception:
        _commit_usage(session)
        raise
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
