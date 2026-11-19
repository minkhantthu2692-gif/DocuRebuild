from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, ProjectDep
from app.core.errors import AppError
from app.db.models import AiConnection, AiModel, utcnow
from app.schemas.ai import (
    AiConnectionCreate,
    AiConnectionDetailOut,
    AiConnectionOut,
    AiConnectionPatch,
    AiConnectionTestIn,
    AiConnectionTestOut,
    AiConnectionsOut,
    AiEquationOut,
    AiEquationRequest,
    AiKeyCreate,
    AiKeyOut,
    AiKeyPatch,
    AiModelFavoriteIn,
    AiModelManualCreate,
    AiModelOut,
    AiOverviewOut,
    AiPreferencesOut,
    AiPreferencesPatch,
    AiProviderOut,
    AiProvidersOut,
    AiRegionProposalsOut,
    AiRegionProposalsRequest,
    AiRouteOut,
    AiRouteUpdate,
    AiRoutesOut,
    AiSuggestionBulkIn,
    AiSuggestionBulkOut,
    AiSuggestionCreate,
    AiSuggestionDecisionIn,
    AiSuggestionDecisionOut,
    AiSuggestionStatus,
    AiSuggestionsOut,
    AiTableOut,
    AiTableRequest,
    AiUsageHistoryOut,
    AiUsageOut,
    AiUsageOutcome,
    AiUsageTask,
)
from app.services import ai as ai_service
from app.services import ai_migrate, ai_providers, ai_router, ai_store, ai_usage, ai_vision
from app.services import projects as project_service
from app.services.projects import touch_project

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai"])


def _ensure_migrated(session: Session) -> None:
    try:
        ai_migrate.run_legacy_ai_migration(session)
    except Exception:
        # A failed migration must not hide the rest of the settings UI. The
        # marker stays pending, so the next start retries.
        logger.exception("Could not migrate legacy AI settings.")
        session.rollback()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    resolved = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return resolved.astimezone(timezone.utc).isoformat()


@router.get("/ai/providers", response_model=AiProvidersOut)
def list_ai_providers() -> dict[str, Any]:
    return {"providers": ai_providers.provider_catalog()}


@router.get("/ai/connections", response_model=AiConnectionsOut)
def list_ai_connections(session: DbSession) -> dict[str, Any]:
    _ensure_migrated(session)
    return {"connections": ai_store.list_connections(session)}


@router.post(
    "/ai/connections",
    response_model=AiConnectionDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_connection(
    payload: AiConnectionCreate, session: DbSession
) -> dict[str, Any]:
    values = ai_store.ConnectionInput(**payload.model_dump())
    return ai_store.create_connection(session, values)


@router.get("/ai/connections/{connection_id}", response_model=AiConnectionDetailOut)
def read_ai_connection(connection_id: str, session: DbSession) -> dict[str, Any]:
    return ai_store.get_connection_payload(session, connection_id)


@router.patch("/ai/connections/{connection_id}", response_model=AiConnectionDetailOut)
def update_ai_connection(
    connection_id: str, payload: AiConnectionPatch, session: DbSession
) -> dict[str, Any]:
    values = ai_store.ConnectionPatch(**payload.model_dump(exclude_unset=True))
    return ai_store.update_connection(session, connection_id, values)


@router.delete(
    "/ai/connections/{connection_id}", status_code=status.HTTP_200_OK
)
def delete_ai_connection(connection_id: str, session: DbSession) -> None:
    ai_store.delete_connection(session, connection_id)


@router.post(
    "/ai/connections/{connection_id}/test", response_model=AiConnectionTestOut
)
def test_ai_connection(
    connection_id: str, session: DbSession, payload: AiConnectionTestIn | None = None
) -> dict[str, Any]:
    connection = ai_store.get_connection(session, connection_id)
    spec = ai_providers.PROVIDER_BY_ID.get(connection.provider)
    if spec is None:
        raise AppError(409, "ai_unknown_provider", "Unknown AI provider.")
    provided = payload.api_key if payload else None
    used_key, secret = ai_store.preferred_key(session, connection, provided)
    if spec.requires_api_key and not secret:
        connection.last_status = "configuration_required"
        connection.last_checked_at = utcnow()
        session.commit()
        return {
            "connection_id": connection.id,
            "status": "configuration_required",
            "provider": connection.provider,
            "base_url": connection.base_url,
            "models_found": 0,
            "cached": True,
            "version": None,
            "error_code": "ai_api_key_required",
            "http_status": None,
            "retry_after_seconds": None,
            "last_checked_at": _iso(connection.last_checked_at),
            "message": "Add an API key before testing this connection.",
        }

    try:
        result = ai_providers.discover_models(
            spec, connection.base_url, api_key=secret
        )
    except ai_providers.ProviderError as exc:
        status_name = {
            "auth": "auth_failed",
            "rate_limit": "rate_limited",
            "server": "unavailable",
            "network": "unavailable",
            "config": "configuration_required",
        }.get(exc.category, "error")
        connection.last_status = status_name
        connection.last_error_code = exc.code
        connection.last_http_status = exc.http_status
        connection.retry_after_seconds = exc.retry_after_seconds
        connection.last_checked_at = utcnow()
        connection.updated_at = utcnow()
        if used_key is not None:
            used_key.last_error_at = utcnow()
            used_key.last_error_code = exc.code
            if exc.category == "auth":
                used_key.auth_failed = True
        session.commit()
        cached = ai_store.list_models(session, connection_id=connection.id)
        return {
            "connection_id": connection.id,
            "status": status_name,
            "provider": connection.provider,
            "base_url": connection.base_url,
            "models_found": len(cached),
            "cached": True,
            "version": None,
            "error_code": exc.code,
            "http_status": exc.http_status,
            "retry_after_seconds": exc.retry_after_seconds,
            "last_checked_at": _iso(connection.last_checked_at),
            "message": exc.message,
        }

    count = ai_store.replace_discovered_models(session, connection, result.models)
    if isinstance(result.version, str) and result.version:
        settings = dict(connection.settings or {})
        settings["provider_version"] = result.version[:120]
        connection.settings = settings
    connection.last_status = "connected"
    connection.last_error_code = None
    connection.last_http_status = None
    connection.retry_after_seconds = None
    connection.last_checked_at = utcnow()
    connection.updated_at = utcnow()
    if used_key is not None:
        used_key.last_used_at = utcnow()
        used_key.last_success_at = utcnow()
        used_key.last_error_code = None
        used_key.cooldown_until = None
        used_key.auth_failed = False
    session.commit()
    return {
        "connection_id": connection.id,
        "status": "connected",
        "provider": connection.provider,
        "base_url": connection.base_url,
        "models_found": count,
        "cached": False,
        "version": result.version,
        "error_code": None,
        "http_status": None,
        "retry_after_seconds": None,
        "last_checked_at": _iso(connection.last_checked_at),
        "message": None,
    }


@router.get("/ai/connections/{connection_id}/keys", response_model=list[AiKeyOut])
def list_ai_keys(connection_id: str, session: DbSession) -> list[dict[str, Any]]:
    return ai_store.list_keys(session, connection_id)


@router.post(
    "/ai/connections/{connection_id}/keys",
    response_model=AiKeyOut,
    status_code=status.HTTP_201_CREATED,
)
def add_ai_key(
    connection_id: str, payload: AiKeyCreate, session: DbSession
) -> dict[str, Any]:
    values = ai_store.KeyInput(**payload.model_dump())
    return ai_store.add_key(session, connection_id, values)


@router.patch(
    "/ai/connections/{connection_id}/keys/{key_id}", response_model=AiKeyOut
)
def update_ai_key(
    connection_id: str, key_id: str, payload: AiKeyPatch, session: DbSession
) -> dict[str, Any]:
    values = ai_store.KeyPatch(**payload.model_dump(exclude_unset=True))
    return ai_store.update_key(session, connection_id, key_id, values)


@router.delete(
    "/ai/connections/{connection_id}/keys/{key_id}",
    status_code=status.HTTP_200_OK,
)
def delete_ai_key(connection_id: str, key_id: str, session: DbSession) -> None:
    ai_store.delete_key(session, connection_id, key_id)


@router.get("/ai/connections/{connection_id}/models", response_model=list[AiModelOut])
def list_connection_models(
    connection_id: str,
    session: DbSession,
    query: str | None = Query(default=None, max_length=200),
    capability: str | None = Query(default=None, pattern="^(text|vision)$"),
    favorites_only: bool = Query(default=False),
    available_only: bool = Query(default=False),
) -> list[dict[str, Any]]:
    return ai_store.list_models(
        session,
        connection_id=connection_id,
        query=query,
        capability=capability,
        favorites_only=favorites_only,
        available_only=available_only,
    )


@router.get("/ai/models", response_model=list[AiModelOut])
def list_all_models(
    session: DbSession,
    query: str | None = Query(default=None, max_length=200),
    connection_id: str | None = Query(default=None),
    capability: str | None = Query(default=None, pattern="^(text|vision)$"),
    favorites_only: bool = Query(default=False),
    available_only: bool = Query(default=False),
) -> list[dict[str, Any]]:
    return ai_store.list_models(
        session,
        connection_id=connection_id,
        query=query,
        capability=capability,
        favorites_only=favorites_only,
        available_only=available_only,
    )


@router.post(
    "/ai/connections/{connection_id}/models",
    response_model=AiModelOut,
    status_code=status.HTTP_201_CREATED,
)
def add_manual_model(
    connection_id: str, payload: AiModelManualCreate, session: DbSession
) -> dict[str, Any]:
    values = ai_store.ManualModelInput(**payload.model_dump())
    return ai_store.add_manual_model(session, connection_id, values)


@router.post(
    "/ai/connections/{connection_id}/models/refresh",
    response_model=AiConnectionTestOut,
)
def refresh_models(
    connection_id: str, session: DbSession, payload: AiConnectionTestIn | None = None
) -> dict[str, Any]:
    return test_ai_connection(connection_id, session, payload)


@router.post(
    "/ai/connections/{connection_id}/models/favorite", response_model=AiModelOut
)
def favorite_model(
    connection_id: str, payload: AiModelFavoriteIn, session: DbSession
) -> dict[str, Any]:
    model_id = payload.model_id
    return ai_store.set_favorite(session, connection_id, model_id, payload.favorite)


@router.post("/ai/models/clear-recent", status_code=status.HTTP_200_OK)
def clear_recent_models(session: DbSession) -> None:
    ai_store.clear_recent_models(session)


@router.get("/ai/routes", response_model=AiRoutesOut)
def list_ai_routes(session: DbSession) -> dict[str, Any]:
    _ensure_migrated(session)
    routes = ai_store.list_routes(session)
    default = next(
        (item["model_id"] for item in routes if item["task"] == ai_store.DEFAULT_ROUTE_TASK),
        None,
    )
    return {"routes": routes, "default_model": default}


@router.put("/ai/routes/{task}", response_model=AiRouteOut)
def update_ai_route(
    task: str, payload: AiRouteUpdate, session: DbSession
) -> dict[str, Any]:
    values = ai_store.RouteInput(**payload.model_dump())
    return ai_store.set_route(session, task, values)


@router.get("/ai/tasks")
def read_ai_task_status(session: DbSession) -> dict[str, Any]:
    _ensure_migrated(session)
    return {"tasks": ai_router.task_status(session)}


@router.get("/ai/preferences", response_model=AiPreferencesOut)
def read_ai_preferences(session: DbSession) -> dict[str, Any]:
    return ai_store.get_preferences(session).model_dump()


@router.patch("/ai/preferences", response_model=AiPreferencesOut)
def update_ai_preferences(
    payload: AiPreferencesPatch, session: DbSession
) -> dict[str, Any]:
    current = ai_store.get_preferences(session)
    values = payload.model_dump(exclude_unset=True)
    merged = {**current.model_dump(), **values}
    updated = ai_store.AiPreferences.model_validate(merged)
    return ai_store.save_preferences(session, updated).model_dump()


@router.get("/ai/overview", response_model=AiOverviewOut)
def read_ai_overview(session: DbSession) -> dict[str, Any]:
    _ensure_migrated(session)
    connections = ai_store.list_connections(session)
    model_count = 0
    key_count = 0
    for connection in connections:
        model_count += int(connection["model_count"])
        key_count += int(connection["key_count"])
    tasks = ai_router.task_status(session)
    preferences = ai_store.get_preferences(session)
    return {
        "connection_count": len(connections),
        "enabled_connection_count": sum(1 for item in connections if item["enabled"]),
        "key_count": key_count,
        "model_count": model_count,
        "configured_task_count": sum(
            1 for item in tasks.values() if item["configured"]
        ),
        "task_count": len(tasks),
        "preferences": preferences.model_dump(),
    }


@router.get("/ai/migration")
def read_ai_migration(session: DbSession) -> dict[str, Any]:
    return ai_migrate.migration_status(session)


@router.get("/ai/usage", response_model=AiUsageOut)
def read_ai_usage(session: DbSession) -> dict[str, Any]:
    preferences = ai_store.get_preferences(session)
    return ai_usage.usage_summary(session, preferences.daily_request_limit)


@router.get("/ai/usage/history", response_model=AiUsageHistoryOut)
def read_ai_usage_history(
    session: DbSession,
    limit: int = Query(ai_usage.HISTORY_LIMIT, ge=1, le=ai_usage.HISTORY_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    outcome: AiUsageOutcome | None = Query(None),
    task: AiUsageTask | None = Query(None),
    connection_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Browse the local ledger beyond the recent rows shown in Settings."""
    return ai_usage.usage_history(
        session,
        limit=limit,
        offset=offset,
        outcome=outcome,
        task=task,
        connection_id=connection_id,
    )


@router.delete("/ai/usage", status_code=status.HTTP_200_OK)
def clear_ai_usage(session: DbSession) -> None:
    ai_store.clear_usage_history(session)


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
    result = ai_vision.propose_regions(
        session,
        directory,
        page_id,
        project_id=project.id,
        confirm_paid=payload.confirm_paid,
    )
    touch_project(session, project)
    return result


@router.post(
    "/projects/{project_id}/elements/{element_id}/ai-equation",
    response_model=AiEquationOut,
)
def create_ai_equation_proposal(
    project: ProjectDep,
    element_id: str,
    payload: AiEquationRequest,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    element = ai_vision.element_context(directory, element_id)
    if element["kind"] != "equation":
        raise AppError(
            409,
            "ai_equation_region_required",
            "Only an equation region can be transcribed.",
        )
    result = ai_vision.transcribe_equation(
        session,
        directory,
        element_id,
        project_id=project.id,
        confirm_paid=payload.confirm_paid,
    )
    touch_project(session, project)
    return result


@router.post(
    "/projects/{project_id}/elements/{element_id}/ai-table",
    response_model=AiTableOut,
)
def create_ai_table_proposal(
    project: ProjectDep,
    element_id: str,
    payload: AiTableRequest,
    session: DbSession,
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    element = ai_vision.element_context(directory, element_id)
    if element["kind"] != "table":
        raise AppError(
            409,
            "ai_table_region_required",
            "Only a table region can be read as a table.",
        )
    result = ai_vision.transcribe_table(
        session,
        directory,
        element_id,
        project_id=project.id,
        confirm_paid=payload.confirm_paid,
    )
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
    suggestion, run = ai_service.create_cleanup_suggestion(
        session,
        directory,
        page_id,
        block_id,
        project_id=project.id,
        confirm_paid=payload.confirm_paid,
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


@router.post(
    "/projects/{project_id}/ai-suggestions/bulk",
    response_model=AiSuggestionBulkOut,
)
def decide_ai_suggestions_bulk(
    project: ProjectDep,
    payload: AiSuggestionBulkIn,
    session: DbSession,
) -> dict[str, Any]:
    """Review many pending proposals without hiding individual refusals."""
    directory = project_service.ensure_project_storage(project)
    result = ai_service.decide_suggestions_bulk(directory, payload.ids, payload.status)
    touch_project(session, project)
    return result
