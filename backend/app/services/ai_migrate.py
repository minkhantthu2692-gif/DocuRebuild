"""Explicit, one-time migration from the legacy AI settings blob.

The previous build kept AI configuration in the ``app_settings`` JSON row and
one encrypted key per task slot. This module converts those values into the
normalized BYOK tables. It runs once, keeps a backup of the old JSON, and copies
legacy secrets only inside the encrypted vault (the plaintext is never read or
written by the migration).

Nothing here runs unless the application starts or an AI endpoint is first used.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AiConnection,
    AiConnectionKey,
    AiModel,
    AiTaskRoute,
    AppSetting,
)
from app.services import ai_providers, ai_secrets

logger = logging.getLogger(__name__)

SETTINGS_KEY = "app"
MIGRATION_KEY = "ai_migration"
BACKUP_KEY = "legacy_ai_settings_backup"
VISION_TASKS = (
    ("region_proposals", "region_model"),
    ("equation_transcription", "equation_model"),
    ("table_structure", "table_model"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _marker(session: Session) -> dict[str, Any] | None:
    row = session.get(AppSetting, MIGRATION_KEY)
    if row is None or not isinstance(row.value, dict):
        return None
    return row.value


def _save_marker(session: Session, value: dict[str, Any]) -> None:
    row = session.get(AppSetting, MIGRATION_KEY)
    if row is None:
        session.add(AppSetting(key=MIGRATION_KEY, value=value, updated_at=_now()))
    else:
        row.value = value
        row.updated_at = _now()


def _legacy_profile(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    provider = value.get("provider")
    model = value.get("model")
    if provider not in ai_providers.PROVIDER_BY_ID:
        return None
    if not isinstance(model, str) or not model.strip():
        return None
    return value


def _connection_for(
    session: Session,
    *,
    provider: str,
    base_url: str,
    allow_remote: bool,
    cost_class: str,
) -> tuple[AiConnection | None, str | None]:
    try:
        resolved = ai_providers.normalize_base_url(
            provider, base_url, allow_remote=allow_remote
        )
    except ai_providers.ProviderError as exc:
        return None, exc.code
    resolved_cost = (
        "local"
        if ai_providers.is_loopback_url(resolved)
        else ("free" if cost_class == "free" else "paid")
    )
    existing = session.execute(
        select(AiConnection).where(
            AiConnection.provider == provider, AiConnection.base_url == resolved
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, None
    spec = ai_providers.PROVIDER_BY_ID[provider]
    connection = AiConnection(
        id=str(uuid.uuid4()),
        provider=provider,
        name=f"{spec.name} (migrated)",
        base_url=resolved,
        allow_remote=allow_remote,
        cost_class=resolved_cost,
        enabled=True,
        rotation_strategy="priority",
        max_attempts=2,
        request_limit=0,
        monthly_budget_usd=None,
        settings={"migrated_from": "legacy_ai_settings"},
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(connection)
    session.flush()
    return connection, None


def _ensure_model(
    session: Session,
    connection: AiConnection,
    model_id: str,
    *,
    vision: bool,
) -> AiModel:
    existing = session.execute(
        select(AiModel).where(
            AiModel.connection_id == connection.id, AiModel.model_id == model_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    model = AiModel(
        id=str(uuid.uuid4()),
        connection_id=connection.id,
        model_id=model_id,
        display_name=None,
        family=None,
        context_window=None,
        input_modalities=["image", "text"] if vision else ["text"],
        output_modalities=["text"],
        supports_tools=None,
        supports_streaming=None,
        pricing=None,
        model_metadata={"migrated_from": "legacy_ai_settings"},
        source="manual",
        available=True,
        discovered_at=_now(),
    )
    session.add(model)
    session.flush()
    return model


def _copy_legacy_key(
    session: Session, connection: AiConnection, task: str
) -> bool:
    """Copy an encrypted key to the new vault slot without exposing plaintext."""
    if not ai_secrets.has_api_key(task):
        return False
    duplicate = session.execute(
        select(AiConnectionKey).where(
            AiConnectionKey.connection_id == connection.id,
            AiConnectionKey.label == f"Migrated {task} key",
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        return True
    key_id = str(uuid.uuid4())
    secret_id = f"connkey:{key_id}"
    if not ai_secrets.copy_secret(task, secret_id):
        return False
    session.add(
        AiConnectionKey(
            id=key_id,
            connection_id=connection.id,
            label=f"Migrated {task} key",
            enabled=True,
            priority=100,
            request_limit=0,
            auth_failed=False,
            created_at=_now(),
        )
    )
    return True


def _set_route(
    session: Session,
    task: str,
    connection: AiConnection | None,
    model_id: str | None,
) -> None:
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
        session.flush()
    if connection is None or not model_id:
        return
    route.connection_id = connection.id
    route.model_id = model_id
    route.updated_at = _now()


def run_legacy_ai_migration(session: Session) -> dict[str, Any]:
    """Convert legacy AI settings once; later calls are a no-op."""
    marker = _marker(session)
    if marker is not None and marker.get("status") in {"done", "empty"}:
        return marker

    app_row = session.get(AppSetting, SETTINGS_KEY)
    stored = dict(app_row.value or {}) if app_row is not None else {}
    legacy = stored.get("ai") if isinstance(stored.get("ai"), dict) else None

    if not legacy:
        _save_marker(
            session,
            {"status": "empty", "migrated_at": _now().isoformat()},
        )
        session.commit()
        return _marker(session) or {}

    # Keep a non-secret backup of the old JSON. API keys were never part of it.
    backup = session.get(AppSetting, BACKUP_KEY)
    if backup is None:
        session.add(
            AppSetting(key=BACKUP_KEY, value=legacy, updated_at=_now())
        )
    else:
        backup.value = legacy
        backup.updated_at = _now()

    text = _legacy_profile(legacy.get("text"))
    vision = _legacy_profile(legacy.get("vision"))
    notices: list[str] = []
    connections_created = 0

    text_connection = None
    text_model = None
    if text is not None:
        provider = str(text["provider"])
        text_model = str(text["model"]).strip()
        text_connection, error = _connection_for(
            session,
            provider=provider,
            base_url=str(text.get("base_url") or ""),
            allow_remote=bool(text.get("allow_remote")),
            cost_class=str(text.get("cost_class") or "local"),
        )
        if error:
            notices.append(f"legacy_text_connection_skipped:{error}")
        elif text_connection is not None:
            _ensure_model(session, text_connection, text_model, vision=False)
            _copy_legacy_key(session, text_connection, "text")
            connections_created += 1

    vision_connection = None
    vision_model = None
    if vision is not None:
        provider = str(vision["provider"])
        vision_model = str(vision["model"]).strip()
        vision_connection, error = _connection_for(
            session,
            provider=provider,
            base_url=str(vision.get("base_url") or ""),
            allow_remote=bool(vision.get("allow_remote")),
            cost_class=str(vision.get("cost_class") or "local"),
        )
        if error:
            notices.append(f"legacy_vision_connection_skipped:{error}")
        elif vision_connection is not None:
            _ensure_model(session, vision_connection, vision_model, vision=True)
            _copy_legacy_key(session, vision_connection, "vision")
            connections_created += 1

    if text_connection is not None and text_model:
        _set_route(session, "ocr_cleanup", text_connection, text_model)
    if vision_connection is not None and vision_model:
        _set_route(session, "region_proposals", vision_connection, vision_model)
        _set_route(
            session, "equation_transcription", vision_connection, vision_model
        )
        _set_route(session, "table_structure", vision_connection, vision_model)
        for task, field in VISION_TASKS:
            override = vision.get(field) if vision else None
            if isinstance(override, str) and override.strip():
                _ensure_model(
                    session, vision_connection, override.strip(), vision=True
                )
                _set_route(
                    session, task, vision_connection, override.strip()
                )

    if app_row is not None:
        stored.pop("ai", None)
        stored.pop("vision_model", None)
        app_row.value = stored
        app_row.updated_at = _now()

    marker_value = {
        "status": "done",
        "migrated_at": _now().isoformat(),
        "connections": connections_created,
        "has_text": text_connection is not None,
        "has_vision": vision_connection is not None,
        "notices": notices,
        "credential_transfer": "encrypted_vault_copy",
    }
    _save_marker(session, marker_value)
    session.commit()
    logger.info(
        "Migrated legacy AI settings: %d connection(s), notices=%s",
        connections_created,
        notices,
    )
    return marker_value


def migration_status(session: Session) -> dict[str, Any]:
    marker = _marker(session)
    if marker is None:
        return {"status": "pending"}
    return marker
