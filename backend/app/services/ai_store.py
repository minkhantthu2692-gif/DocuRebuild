"""Persistence and validation for the unified BYOK AI configuration.

Everything the application needs to know about providers, credentials, models
and task routing lives here. Call sites never read provider settings directly
and never receive a decrypted API key.

API keys are stored only in the encrypted vault (see ``ai_secrets``). This
module stores non-secret metadata: labels, priorities, health and timestamps.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    AiConnection,
    AiConnectionKey,
    AiModel,
    AiModelPreference,
    AiTaskRoute,
    AiUsage,
    AppSetting,
    utcnow,
)
from app.services import ai_providers, ai_secrets

logger = logging.getLogger(__name__)

DEFAULT_ROUTE_TASK = "default"
ROTATION_STRATEGIES = ("priority", "failover", "round_robin", "least_recent", "least_usage")
COST_CLASSES = ("local", "free", "paid")

SECRET_ID_PREFIX = "connkey:"


@dataclass(frozen=True)
class TaskSpec:
    id: str
    label: str
    capability: str  # "text" or "vision"


TASKS: tuple[TaskSpec, ...] = (
    TaskSpec("ocr_cleanup", "OCR text cleanup", "text"),
    TaskSpec("region_proposals", "Region proposals", "vision"),
    TaskSpec("equation_transcription", "Equation transcription", "vision"),
    TaskSpec("table_structure", "Table reading", "vision"),
)
TASK_BY_ID = {task.id: task for task in TASKS}
TASK_IDS = tuple(task.id for task in TASKS)


def task_spec(task: str) -> TaskSpec:
    spec = TASK_BY_ID.get(task)
    if spec is None:
        raise AppError(422, "ai_unknown_task", "Unknown AI task.")
    return spec


def secret_id_for_key(key_id: str) -> str:
    return f"{SECRET_ID_PREFIX}{key_id}"


def _now() -> datetime:
    return utcnow()


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as the UTC they were stored as."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    resolved = _as_utc(value)
    return resolved.isoformat() if resolved is not None else None


def _provider_error(exc: ai_providers.ProviderError) -> AppError:
    status = 422
    if exc.category in {"network", "server"}:
        status = 502
    elif exc.category == "rate_limit":
        status = 429
    elif exc.category == "auth":
        status = 401
    elif exc.code == "ai_remote_not_allowed":
        # Missing consent is a refusal, not malformed input.
        status = 403
    return AppError(status, exc.code, exc.message)


# ---------------------------------------------------------------------------
# Validation models
# ---------------------------------------------------------------------------


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=120)
    base_url: str = Field(default="", max_length=500)
    allow_remote: bool = False
    cost_class: str = "local"
    enabled: bool = True
    rotation_strategy: str = "priority"
    max_attempts: int = Field(default=2, ge=1, le=10)
    request_limit: int = Field(default=0, ge=0, le=100_000)
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", "name", "base_url", "rotation_strategy", "cost_class")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class ConnectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    allow_remote: bool | None = None
    cost_class: str | None = None
    enabled: bool | None = None
    rotation_strategy: str | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    request_limit: int | None = Field(default=None, ge=0, le=100_000)
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)
    settings: dict[str, Any] | None = None

    @field_validator("name", "base_url", "rotation_strategy", "cost_class")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="", max_length=80)
    api_key: str = Field(min_length=1, max_length=1024)
    priority: int = Field(default=100, ge=0, le=10_000)
    enabled: bool = True
    request_limit: int = Field(default=0, ge=0, le=100_000)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        return value.strip()


class KeyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=80)
    priority: int | None = Field(default=None, ge=0, le=10_000)
    enabled: bool | None = None
    request_limit: int | None = Field(default=None, ge=0, le=100_000)
    auth_failed: bool | None = None

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()


class ManualModelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    context_window: int | None = Field(default=None, ge=1)
    input_modalities: list[str] | None = None
    output_modalities: list[str] | None = None

    @field_validator("model_id", "display_name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()

    @field_validator("input_modalities", "output_modalities")
    @classmethod
    def _clean_modalities(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = sorted({item.strip().lower() for item in value if item.strip()})
        return cleaned or None


class RouteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str | None = None
    model_id: str | None = Field(default=None, max_length=200)
    fallback_connection_id: str | None = None
    fallback_model_id: str | None = Field(default=None, max_length=200)
    temperature: float = Field(default=0.0, ge=0, le=2)
    timeout_seconds: int = Field(default=60, ge=5, le=600)
    request_limit: int = Field(default=0, ge=0, le=100_000)

    @field_validator("model_id", "fallback_model_id")
    @classmethod
    def _strip_model(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()


# ---------------------------------------------------------------------------
# Global AI preferences (stored beside the other application settings)
# ---------------------------------------------------------------------------

PREFERENCES_KEY = "ai_preferences"


class AiPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Rolling 24-hour cap across every connection and task. Zero is unlimited.
    daily_request_limit: int = Field(default=0, ge=0, le=100_000)
    # Optional monthly spend guard. Only enforced when a verified cost exists.
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)


def get_preferences(session: Session) -> AiPreferences:
    row = session.get(AppSetting, PREFERENCES_KEY)
    if row is None or not isinstance(row.value, dict):
        return AiPreferences()
    try:
        return AiPreferences.model_validate(row.value)
    except ValidationError:
        logger.warning("Stored AI preferences were invalid; using defaults.")
        return AiPreferences()


def save_preferences(session: Session, values: AiPreferences) -> AiPreferences:
    row = session.get(AppSetting, PREFERENCES_KEY)
    payload = values.model_dump()
    if row is None:
        session.add(AppSetting(key=PREFERENCES_KEY, value=payload, updated_at=_now()))
    else:
        row.value = payload
        row.updated_at = _now()
    session.commit()
    return values


# ---------------------------------------------------------------------------
# Serialization (never includes a secret)
# ---------------------------------------------------------------------------


def key_payload(key: AiConnectionKey) -> dict[str, Any]:
    cooldown = _as_utc(key.cooldown_until)
    cooling = cooldown is not None and cooldown > _now()
    if not key.enabled:
        status = "disabled"
    elif key.auth_failed:
        status = "auth_failed"
    elif cooling:
        status = "rate_limited"
    elif key.last_error_code:
        status = "error"
    else:
        status = "ready"
    return {
        "id": key.id,
        "label": key.label,
        "enabled": key.enabled,
        "priority": key.priority,
        "request_limit": key.request_limit,
        "auth_failed": key.auth_failed,
        "status": status,
        "has_secret": ai_secrets.has_secret(secret_id_for_key(key.id)),
        "last_used_at": _iso(key.last_used_at),
        "last_success_at": _iso(key.last_success_at),
        "last_error_at": _iso(key.last_error_at),
        "last_error_code": key.last_error_code,
        "cooldown_until": _iso(key.cooldown_until),
        "created_at": _iso(key.created_at),
    }


def model_payload(model: AiModel, preference: AiModelPreference | None) -> dict[str, Any]:
    return {
        "id": model.id,
        "connection_id": model.connection_id,
        "model_id": model.model_id,
        "display_name": model.display_name,
        "family": model.family,
        "context_window": model.context_window,
        "input_modalities": model.input_modalities,
        "output_modalities": model.output_modalities,
        "supports_tools": model.supports_tools,
        "supports_streaming": model.supports_streaming,
        "pricing": model.pricing,
        "metadata": model.model_metadata,
        "source": model.source,
        "available": model.available,
        "favorite": bool(preference and preference.favorite),
        "last_used_at": _iso(preference.last_used_at) if preference else None,
        "discovered_at": _iso(model.discovered_at),
    }


def connection_status(connection: AiConnection, *, key_count: int) -> str:
    if not connection.enabled:
        return "disabled"
    if connection.last_status:
        return connection.last_status
    spec = ai_providers.PROVIDER_BY_ID.get(connection.provider)
    if spec is None:
        return "configuration_required"
    if spec.requires_api_key and key_count == 0:
        return "configuration_required"
    # Models are discovered by testing the connection; a key alone is enough to
    # attempt that test, so the remaining step is "untested", not "incomplete".
    return "untested"


def _connection_payload(
    session: Session,
    connection: AiConnection,
    *,
    include_keys: bool = False,
) -> dict[str, Any]:
    keys = list(
        session.execute(
            select(AiConnectionKey)
            .where(AiConnectionKey.connection_id == connection.id)
            .order_by(AiConnectionKey.priority, AiConnectionKey.created_at)
        )
        .scalars()
        .all()
    )
    models = list(
        session.execute(
            select(AiModel).where(AiModel.connection_id == connection.id)
        )
        .scalars()
        .all()
    )
    spec = ai_providers.PROVIDER_BY_ID.get(connection.provider)
    payload: dict[str, Any] = {
        "id": connection.id,
        "provider": connection.provider,
        "provider_name": spec.name if spec else connection.provider,
        "provider_kind": spec.kind if spec else "openai",
        "name": connection.name,
        "base_url": connection.base_url,
        "allow_remote": connection.allow_remote,
        "cost_class": connection.cost_class,
        "enabled": connection.enabled,
        "rotation_strategy": connection.rotation_strategy,
        "max_attempts": connection.max_attempts,
        "request_limit": connection.request_limit,
        "monthly_budget_usd": connection.monthly_budget_usd,
        "settings": connection.settings or {},
        "status": connection_status(connection, key_count=len(keys)),
        "last_error_code": connection.last_error_code,
        "last_http_status": connection.last_http_status,
        "retry_after_seconds": connection.retry_after_seconds,
        "last_checked_at": _iso(connection.last_checked_at),
        "created_at": _iso(connection.created_at),
        "updated_at": _iso(connection.updated_at),
        "key_count": len(keys),
        "enabled_key_count": sum(1 for key in keys if key.enabled),
        "model_count": sum(1 for model in models if model.available),
        "requires_api_key": bool(spec and spec.requires_api_key),
    }
    if include_keys:
        payload["keys"] = [key_payload(key) for key in keys]
    return payload


def list_connections(session: Session) -> list[dict[str, Any]]:
    connections = list(
        session.execute(
            select(AiConnection).order_by(AiConnection.created_at, AiConnection.name)
        )
        .scalars()
        .all()
    )
    return [_connection_payload(session, connection) for connection in connections]


def get_connection(session: Session, connection_id: str) -> AiConnection:
    connection = session.get(AiConnection, connection_id)
    if connection is None:
        raise AppError(404, "ai_connection_not_found", "AI connection not found.")
    return connection


def get_connection_payload(
    session: Session, connection_id: str, *, include_keys: bool = True
) -> dict[str, Any]:
    return _connection_payload(
        session, get_connection(session, connection_id), include_keys=include_keys
    )


def _resolve_connection_values(
    provider_id: str,
    *,
    base_url: str,
    allow_remote: bool,
    cost_class: str,
) -> tuple[str, bool, str]:
    if provider_id not in ai_providers.PROVIDER_BY_ID:
        raise AppError(422, "ai_unknown_provider", "Unknown AI provider.")
    if cost_class not in COST_CLASSES:
        raise AppError(422, "ai_invalid_cost_class", "Choose a valid cost class.")
    try:
        resolved_url = ai_providers.normalize_base_url(
            provider_id, base_url, allow_remote=allow_remote
        )
    except ai_providers.ProviderError as exc:
        raise _provider_error(exc) from exc
    loopback = ai_providers.is_loopback_url(resolved_url)
    # A loopback endpoint is always local inference. Remote endpoints keep the
    # user's free/paid declaration, because the app never guesses a price.
    resolved_cost = "local" if loopback else ("free" if cost_class == "free" else "paid")
    if not loopback and not allow_remote:
        raise AppError(
            403,
            "ai_remote_not_allowed",
            "Enable remote transmission consent for this connection first.",
        )
    return resolved_url, loopback, resolved_cost


def create_connection(session: Session, payload: ConnectionInput) -> dict[str, Any]:
    values = payload.model_dump()
    if not values["name"]:
        spec = ai_providers.PROVIDER_BY_ID.get(values["provider"])
        values["name"] = spec.name if spec else values["provider"]
    resolved_url, _loopback, cost_class = _resolve_connection_values(
        values["provider"],
        base_url=values["base_url"],
        allow_remote=values["allow_remote"],
        cost_class=values["cost_class"],
    )
    if values["rotation_strategy"] not in ROTATION_STRATEGIES:
        raise AppError(422, "ai_invalid_rotation", "Choose a valid rotation strategy.")
    connection = AiConnection(
        id=str(uuid.uuid4()),
        provider=values["provider"],
        name=values["name"],
        base_url=resolved_url,
        allow_remote=values["allow_remote"],
        cost_class=cost_class,
        enabled=values["enabled"],
        rotation_strategy=values["rotation_strategy"],
        max_attempts=values["max_attempts"],
        request_limit=values["request_limit"],
        monthly_budget_usd=values["monthly_budget_usd"],
        settings=values["settings"] or {},
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(connection)
    session.commit()
    return _connection_payload(session, connection, include_keys=True)


def update_connection(
    session: Session, connection_id: str, payload: ConnectionPatch
) -> dict[str, Any]:
    connection = get_connection(session, connection_id)
    values = payload.model_dump(exclude_none=True)
    new_name = values.get("name", connection.name)
    if not new_name.strip():
        raise AppError(422, "ai_connection_name_required", "Enter a connection name.")
    new_rotation = values.get("rotation_strategy", connection.rotation_strategy)
    if new_rotation not in ROTATION_STRATEGIES:
        raise AppError(422, "ai_invalid_rotation", "Choose a valid rotation strategy.")
    new_url, _loopback, cost_class = _resolve_connection_values(
        connection.provider,
        base_url=values.get("base_url", connection.base_url),
        allow_remote=values.get("allow_remote", connection.allow_remote),
        cost_class=values.get("cost_class", connection.cost_class),
    )

    connection.name = new_name
    connection.base_url = new_url
    connection.allow_remote = values.get("allow_remote", connection.allow_remote)
    connection.cost_class = cost_class
    connection.enabled = values.get("enabled", connection.enabled)
    connection.rotation_strategy = new_rotation
    connection.max_attempts = values.get("max_attempts", connection.max_attempts)
    connection.request_limit = values.get("request_limit", connection.request_limit)
    if "monthly_budget_usd" in values:
        connection.monthly_budget_usd = values["monthly_budget_usd"]
    if "settings" in values:
        connection.settings = values["settings"] or {}
    connection.updated_at = _now()
    # A changed endpoint invalidates the previous health result, but the cached
    # discovered model list is kept and clearly marked unavailable until a new
    # test succeeds.
    if new_url != connection.base_url or connection.last_status in {
        "auth_failed",
        "rate_limited",
    }:
        connection.last_status = None
    session.commit()
    return _connection_payload(session, connection, include_keys=True)


def delete_connection(session: Session, connection_id: str) -> None:
    connection = get_connection(session, connection_id)
    keys = list(
        session.execute(
            select(AiConnectionKey).where(AiConnectionKey.connection_id == connection.id)
        )
        .scalars()
        .all()
    )
    for key in keys:
        ai_secrets.clear_secret(secret_id_for_key(key.id))
    # Routes that referenced this connection become unconfigured rather than
    # silently pointing at a different provider.
    routes = list(session.execute(select(AiTaskRoute)).scalars().all())
    for route in routes:
        if route.connection_id == connection.id:
            route.connection_id = None
            route.model_id = None
            route.updated_at = _now()
        if route.fallback_connection_id == connection.id:
            route.fallback_connection_id = None
            route.fallback_model_id = None
            route.updated_at = _now()
    session.delete(connection)
    session.commit()


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def list_keys(session: Session, connection_id: str) -> list[dict[str, Any]]:
    get_connection(session, connection_id)
    rows = (
        session.execute(
            select(AiConnectionKey)
            .where(AiConnectionKey.connection_id == connection_id)
            .order_by(AiConnectionKey.priority, AiConnectionKey.created_at)
        )
        .scalars()
        .all()
    )
    return [key_payload(row) for row in rows]


def add_key(session: Session, connection_id: str, payload: KeyInput) -> dict[str, Any]:
    connection = get_connection(session, connection_id)
    cleaned = ai_secrets.clean_api_key(payload.api_key)
    key_id = str(uuid.uuid4())
    key = AiConnectionKey(
        id=key_id,
        connection_id=connection.id,
        label=payload.label,
        enabled=payload.enabled,
        priority=payload.priority,
        request_limit=payload.request_limit,
        auth_failed=False,
        created_at=_now(),
    )
    ai_secrets.set_secret(secret_id_for_key(key_id), cleaned)
    session.add(key)
    connection.last_status = None
    connection.updated_at = _now()
    session.commit()
    return key_payload(key)


def update_key(
    session: Session, connection_id: str, key_id: str, payload: KeyPatch
) -> dict[str, Any]:
    key = session.get(AiConnectionKey, key_id)
    if key is None or key.connection_id != connection_id:
        raise AppError(404, "ai_key_not_found", "API key not found.")
    values = payload.model_dump(exclude_none=True)
    for field in ("label", "priority", "enabled", "request_limit"):
        if field in values:
            setattr(key, field, values[field])
    if values.get("auth_failed") is False:
        key.auth_failed = False
        key.last_error_code = None
        key.cooldown_until = None
    session.commit()
    return key_payload(key)


def delete_key(session: Session, connection_id: str, key_id: str) -> None:
    key = session.get(AiConnectionKey, key_id)
    if key is None or key.connection_id != connection_id:
        raise AppError(404, "ai_key_not_found", "API key not found.")
    ai_secrets.clear_secret(secret_id_for_key(key.id))
    session.delete(key)
    session.commit()


def resolve_key_secret(key: AiConnectionKey) -> str | None:
    return ai_secrets.get_secret(secret_id_for_key(key.id))


def preferred_key(
    session: Session, connection: AiConnection, provided: str | None = None
) -> tuple[AiConnectionKey | None, str | None]:
    """Choose one key row for a connection test, preferring a just-typed key."""
    if provided:
        return None, ai_secrets.clean_api_key(provided)
    rows = (
        session.execute(
            select(AiConnectionKey)
            .where(
                AiConnectionKey.connection_id == connection.id,
                AiConnectionKey.enabled.is_(True),
                AiConnectionKey.auth_failed.is_(False),
            )
            .order_by(AiConnectionKey.priority, AiConnectionKey.created_at)
        )
        .scalars()
        .all()
    )
    for key in rows:
        secret = resolve_key_secret(key)
        if secret:
            return key, secret
    return None, None


def preferred_key_secret(
    session: Session, connection: AiConnection, provided: str | None = None
) -> str | None:
    """Choose one key for a connection test, preferring a just-typed key."""
    return preferred_key(session, connection, provided)[1]


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------


def _preference_map(session: Session, connection_id: str) -> dict[str, AiModelPreference]:
    rows = (
        session.execute(
            select(AiModelPreference).where(
                AiModelPreference.connection_id == connection_id
            )
        )
        .scalars()
        .all()
    )
    return {row.model_id: row for row in rows}


def list_models(
    session: Session,
    *,
    connection_id: str | None = None,
    query: str | None = None,
    capability: str | None = None,
    favorites_only: bool = False,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    statement = select(AiModel)
    if connection_id:
        get_connection(session, connection_id)
        statement = statement.where(AiModel.connection_id == connection_id)
    if available_only:
        statement = statement.where(AiModel.available.is_(True))
    models = list(session.execute(statement.order_by(AiModel.model_id)).scalars().all())
    preferences = _preference_map(session, connection_id) if connection_id else {}
    if not connection_id and models:
        preferences = {}
        for model in models:
            preferences.update(
                {
                    f"{model.connection_id}:{row.model_id}": row
                    for row in session.execute(
                        select(AiModelPreference).where(
                            AiModelPreference.connection_id == model.connection_id
                        )
                    )
                    .scalars()
                    .all()
                }
            )
    needle = (query or "").strip().lower()
    result: list[dict[str, Any]] = []
    for model in models:
        preference = (
            preferences.get(model.model_id)
            if connection_id
            else preferences.get(f"{model.connection_id}:{model.model_id}")
        )
        if favorites_only and not (preference and preference.favorite):
            continue
        if capability == "vision":
            modalities = model.input_modalities
            if modalities is not None and "image" not in modalities:
                continue
        if capability == "text":
            modalities = model.output_modalities
            if modalities is not None and "text" not in modalities:
                continue
        if needle:
            haystack = " ".join(
                value
                for value in (model.model_id, model.display_name, model.family)
                if value
            ).lower()
            if needle not in haystack:
                continue
        result.append(model_payload(model, preference))
    return result


def _upsert_model(
    session: Session,
    connection: AiConnection,
    entry: dict[str, Any],
    *,
    source: str,
) -> AiModel:
    model_id = entry["model_id"]
    model = session.execute(
        select(AiModel).where(
            AiModel.connection_id == connection.id, AiModel.model_id == model_id
        )
    ).scalar_one_or_none()
    if model is None:
        model = AiModel(
            id=str(uuid.uuid4()),
            connection_id=connection.id,
            model_id=model_id,
            source=source,
            discovered_at=_now(),
        )
        session.add(model)
    model.display_name = entry.get("display_name")
    model.family = entry.get("family")
    model.context_window = entry.get("context_window")
    model.input_modalities = entry.get("input_modalities")
    model.output_modalities = entry.get("output_modalities")
    model.supports_tools = entry.get("supports_tools")
    model.supports_streaming = entry.get("supports_streaming")
    model.pricing = entry.get("pricing")
    model.model_metadata = entry.get("metadata") or entry.get("model_metadata")
    model.source = source
    model.available = True
    model.discovered_at = _now()
    return model


def replace_discovered_models(
    session: Session, connection: AiConnection, entries: Iterable[dict[str, Any]]
) -> int:
    """Replace the discovered half of a catalog while keeping manual entries.

    A model missing from the newest listing is marked unavailable instead of
    deleted, so a task route keeps referring to a known model id and the UI can
    explain that the provider no longer lists it.
    """
    discovered_ids: set[str] = set()
    count = 0
    for entry in entries:
        _upsert_model(session, connection, entry, source="discovered")
        discovered_ids.add(entry["model_id"])
        count += 1
    existing = (
        session.execute(
            select(AiModel).where(
                AiModel.connection_id == connection.id, AiModel.source == "discovered"
            )
        )
        .scalars()
        .all()
    )
    for model in existing:
        if model.model_id not in discovered_ids:
            model.available = False
    connection.last_checked_at = _now()
    connection.updated_at = _now()
    session.commit()
    return count


def add_manual_model(
    session: Session, connection_id: str, payload: ManualModelInput
) -> dict[str, Any]:
    connection = get_connection(session, connection_id)
    spec = ai_providers.PROVIDER_BY_ID.get(connection.provider)
    if spec is None or not spec.allows_manual_models:
        raise AppError(
            409,
            "ai_manual_model_unsupported",
            "This provider discovers its models automatically. Refresh the model list instead.",
        )
    existing = session.execute(
        select(AiModel).where(
            AiModel.connection_id == connection.id,
            AiModel.model_id == payload.model_id,
        )
    ).scalar_one_or_none()
    if existing is not None and existing.source == "discovered":
        raise AppError(409, "ai_model_exists", "That model is already in the catalog.")
    entry = {
        "model_id": payload.model_id,
        "display_name": payload.display_name,
        "context_window": payload.context_window,
        "input_modalities": payload.input_modalities,
        "output_modalities": payload.output_modalities,
    }
    model = _upsert_model(session, connection, entry, source="manual")
    session.commit()
    return model_payload(model, None)


def set_favorite(
    session: Session, connection_id: str, model_id: str, favorite: bool
) -> dict[str, Any]:
    get_connection(session, connection_id)
    preference = session.get(AiModelPreference, (connection_id, model_id))
    if preference is None:
        preference = AiModelPreference(
            connection_id=connection_id,
            model_id=model_id,
            favorite=favorite,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(preference)
    else:
        preference.favorite = favorite
        preference.updated_at = _now()
    session.commit()
    model = session.execute(
        select(AiModel).where(
            AiModel.connection_id == connection_id, AiModel.model_id == model_id
        )
    ).scalar_one_or_none()
    if model is None:
        raise AppError(404, "ai_model_not_found", "Model not found.")
    return model_payload(model, preference)


def clear_recent_models(session: Session) -> None:
    """Clear only the last-used timestamps, never favorites or the catalog."""
    preferences = session.execute(select(AiModelPreference)).scalars().all()
    for preference in preferences:
        preference.last_used_at = None
        preference.updated_at = _now()
    session.commit()


# ---------------------------------------------------------------------------
# Task routes
# ---------------------------------------------------------------------------


def _route_payload(
    session: Session,
    route: AiTaskRoute,
    *,
    task: str,
) -> dict[str, Any]:
    connection = (
        session.get(AiConnection, route.connection_id) if route.connection_id else None
    )
    fallback = (
        session.get(AiConnection, route.fallback_connection_id)
        if route.fallback_connection_id
        else None
    )
    model = None
    if connection is not None and route.model_id:
        model = session.execute(
            select(AiModel).where(
                AiModel.connection_id == connection.id,
                AiModel.model_id == route.model_id,
            )
        ).scalar_one_or_none()
    spec = TASK_BY_ID.get(task)
    warnings: list[str] = []
    configured = bool(connection and route.model_id and connection.enabled)
    if connection is not None and not connection.enabled:
        warnings.append("connection_disabled")
    if connection is None:
        warnings.append("connection_required")
    if route.model_id and model is None:
        warnings.append("model_not_in_catalog")
    if model is not None and not model.available:
        warnings.append("model_unavailable")
    if (
        model is not None
        and spec is not None
        and spec.capability == "vision"
        and model.input_modalities is not None
        and "image" not in model.input_modalities
    ):
        warnings.append("vision_unsupported")
    return {
        "task": task,
        "connection_id": route.connection_id,
        "connection_name": connection.name if connection else None,
        "connection_status": (
            _connection_payload(session, connection)["status"] if connection else None
        ),
        "cost_class": connection.cost_class if connection else None,
        "model_id": route.model_id,
        "model_display_name": model.display_name if model else None,
        "model_source": model.source if model else None,
        "capability": spec.capability if spec else "text",
        "fallback_connection_id": route.fallback_connection_id,
        "fallback_connection_name": fallback.name if fallback else None,
        "fallback_model_id": route.fallback_model_id,
        "temperature": route.temperature,
        "timeout_seconds": route.timeout_seconds,
        "request_limit": route.request_limit,
        "configured": configured,
        "warnings": warnings,
        "updated_at": _iso(route.updated_at),
    }


def _ensure_route_row(session: Session, task: str) -> AiTaskRoute:
    route = session.get(AiTaskRoute, task)
    if route is None:
        route = AiTaskRoute(
            task=task,
            temperature=0.0,
            timeout_seconds=60,
            request_limit=0,
            updated_at=_now(),
        )
        session.add(route)
    return route


def list_routes(session: Session) -> list[dict[str, Any]]:
    rows = {row.task: row for row in session.execute(select(AiTaskRoute)).scalars().all()}
    result: list[dict[str, Any]] = []
    for task in (DEFAULT_ROUTE_TASK, *TASK_IDS):
        route = rows.get(task)
        if route is None:
            route = AiTaskRoute(
                task=task,
                temperature=0.0,
                timeout_seconds=60,
                request_limit=0,
                updated_at=_now(),
            )
        result.append(_route_payload(session, route, task=task))
    return result


def _validate_model_for_task(
    session: Session,
    connection: AiConnection,
    model_id: str,
    task: str,
) -> None:
    spec = TASK_BY_ID.get(task)
    if task == DEFAULT_ROUTE_TASK:
        return
    if spec is None:
        raise AppError(422, "ai_unknown_task", "Unknown AI task.")
    model = session.execute(
        select(AiModel).where(
            AiModel.connection_id == connection.id, AiModel.model_id == model_id
        )
    ).scalar_one_or_none()
    if model is None:
        raise AppError(
            409,
            "ai_model_not_in_catalog",
            "Choose a model discovered from this connection, or add it manually.",
        )
    if not model.available:
        raise AppError(
            409,
            "ai_model_unavailable",
            "The provider no longer lists this model. Refresh the model list first.",
        )
    if spec.capability == "vision":
        modalities = model.input_modalities
        if modalities is not None and "image" not in modalities:
            raise AppError(
                409,
                "ai_model_missing_vision",
                "This model does not accept image input. Choose a vision-capable model.",
            )
    else:
        modalities = model.output_modalities
        if modalities is not None and "text" not in modalities:
            raise AppError(
                409,
                "ai_model_missing_text",
                "This model does not produce text. Choose a text-capable model.",
            )


def set_route(session: Session, task: str, payload: RouteInput) -> dict[str, Any]:
    if task != DEFAULT_ROUTE_TASK:
        task_spec(task)
    route = _ensure_route_row(session, task)
    if payload.connection_id:
        connection = get_connection(session, payload.connection_id)
        if not payload.model_id:
            raise AppError(422, "ai_model_required", "Choose a model for this task.")
        _validate_model_for_task(session, connection, payload.model_id, task)
        route.connection_id = connection.id
        route.model_id = payload.model_id
    else:
        route.connection_id = None
        route.model_id = None
    if payload.fallback_connection_id:
        fallback = get_connection(session, payload.fallback_connection_id)
        if not payload.fallback_model_id:
            raise AppError(
                422, "ai_model_required", "Choose a model for the fallback connection."
            )
        _validate_model_for_task(
            session, fallback, payload.fallback_model_id, task
        )
        route.fallback_connection_id = fallback.id
        route.fallback_model_id = payload.fallback_model_id
    else:
        route.fallback_connection_id = None
        route.fallback_model_id = None
    route.temperature = payload.temperature
    route.timeout_seconds = payload.timeout_seconds
    route.request_limit = payload.request_limit
    route.updated_at = _now()
    session.commit()
    return _route_payload(session, route, task=task)


def effective_route(session: Session, task: str) -> AiTaskRoute | None:
    route = session.get(AiTaskRoute, task)
    if route is not None and route.connection_id and route.model_id:
        return route
    fallback = session.get(AiTaskRoute, DEFAULT_ROUTE_TASK)
    if fallback is not None and fallback.connection_id and fallback.model_id:
        if task != DEFAULT_ROUTE_TASK:
            spec = TASK_BY_ID.get(task)
            if spec is not None:
                connection = session.get(AiConnection, fallback.connection_id)
                if connection is not None:
                    _validate_model_for_task(
                        session, connection, fallback.model_id, task
                    )
        return fallback
    return None


def touch_model_use(session: Session, connection_id: str, model_id: str) -> None:
    preference = session.get(AiModelPreference, (connection_id, model_id))
    if preference is None:
        preference = AiModelPreference(
            connection_id=connection_id,
            model_id=model_id,
            favorite=False,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(preference)
    preference.last_used_at = _now()
    preference.updated_at = _now()


def usage_count(session: Session, **filters: Any) -> int:
    statement = select(func.count()).select_from(AiUsage)
    for field, value in filters.items():
        column = getattr(AiUsage, field, None)
        if column is not None and value is not None:
            statement = statement.where(column == value)
    return int(session.execute(statement).scalar_one())


def clear_usage_history(session: Session) -> None:
    session.execute(delete(AiUsage))
    session.commit()
