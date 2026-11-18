from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AppSetting, utcnow
from app.schemas.settings import AppSettings, SettingsUpdate
from app.services import ai_secrets

logger = logging.getLogger(__name__)

SETTINGS_KEY = "app"

# `has_api_key` is derived from the encrypted secret store, not from this row.
_DERIVED_AI_FIELDS = ("has_api_key",)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        elif value is not None:
            merged[key] = value
    return merged


def _migrate_legacy_ai(merged: dict[str, Any]) -> dict[str, Any]:
    """Map a stored single ``vision_model`` string onto a vision task profile.

    Older settings kept one vision model next to a shared text server. Copying it
    into ``vision`` preserves the exact provider, URL and consent that were in use,
    and the legacy key disappears the next time settings are saved.
    """
    ai = merged.get("ai")
    if not isinstance(ai, dict):
        return merged
    legacy = ai.pop("vision_model", None)
    if not isinstance(legacy, str) or not legacy.strip():
        return merged
    vision = ai.get("vision")
    if isinstance(vision, dict) and str(vision.get("model") or "").strip():
        return merged
    text = ai.get("text") if isinstance(ai.get("text"), dict) else {}
    ai["vision"] = {
        "provider": text.get("provider", "ollama"),
        "base_url": text.get("base_url", ""),
        "model": legacy.strip(),
        "allow_remote": bool(text.get("allow_remote", False)),
    }
    return merged


def _overlay_api_keys(settings: AppSettings) -> AppSettings:
    for task in ai_secrets.TASKS:
        profile = getattr(settings.ai, task)
        profile.has_api_key = ai_secrets.has_api_key(task)
    return settings


def _take_key_actions(patch_values: dict[str, Any]) -> list[tuple[str, str | None]]:
    """Remove write-only key fields from the settings patch.

    Each entry is ``(task, key)``; a ``None`` key means the stored key must be
    cleared. The caller applies them only after the rest of the patch validates.
    """
    actions: list[tuple[str, str | None]] = []
    ai_patch = patch_values.get("ai")
    if not isinstance(ai_patch, dict):
        return actions
    for task in ai_secrets.TASKS:
        profile_patch = ai_patch.get(task)
        if not isinstance(profile_patch, dict):
            continue
        api_key = profile_patch.pop("api_key", None)
        clear = profile_patch.pop("clear_api_key", None)
        if isinstance(api_key, str):
            actions.append((task, api_key))
        elif clear:
            actions.append((task, None))
    return actions


def get_app_settings(session: Session) -> AppSettings:
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        return _overlay_api_keys(AppSettings())
    merged = _migrate_legacy_ai(
        _deep_merge(AppSettings().model_dump(), row.value or {})
    )
    try:
        settings = AppSettings.model_validate(merged)
    except ValidationError:
        logger.warning("Stored settings were invalid; falling back to defaults.")
        settings = AppSettings()
    return _overlay_api_keys(settings)


def update_app_settings(session: Session, patch: SettingsUpdate) -> AppSettings:
    current = get_app_settings(session)
    patch_values = patch.model_dump(exclude_none=True, exclude_unset=True)
    key_actions = _take_key_actions(patch_values)
    merged = _deep_merge(current.model_dump(), patch_values)
    try:
        validated = AppSettings.model_validate(merged)
    except ValidationError as exc:
        raise AppError(422, "invalid_settings", "Settings values are not valid.") from exc

    for task, api_key in key_actions:
        if api_key is None:
            ai_secrets.clear_api_key(task)
        else:
            ai_secrets.set_api_key(task, api_key)

    stored = validated.model_dump()
    for task in ai_secrets.TASKS:
        for field in _DERIVED_AI_FIELDS:
            stored["ai"][task].pop(field, None)
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        row = AppSetting(key=SETTINGS_KEY, value=stored, updated_at=utcnow())
        session.add(row)
    else:
        row.value = stored
        row.updated_at = utcnow()
    session.commit()
    return _overlay_api_keys(validated)
