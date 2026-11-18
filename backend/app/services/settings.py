from __future__ import annotations

import copy
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AppSetting, utcnow
from app.schemas.settings import AppSettings, SettingsUpdate
from app.services import ai as ai_service
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


def _infer_cost_classes(stored: dict[str, Any]) -> dict[str, Any]:
    """Classify profiles saved before cost classes existed.

    A profile on loopback is local inference. Anything else is treated as paid,
    because a remote server may bill the user and must not be assumed free.
    Explicitly saved cost classes are left untouched.
    """
    ai = stored.get("ai")
    if not isinstance(ai, dict):
        return stored
    for task in ai_secrets.TASKS:
        profile = ai.get(task)
        if not isinstance(profile, dict) or "cost_class" in profile:
            continue
        provider = profile.get("provider", "ollama")
        base_url = profile.get("base_url", "")
        local = (
            isinstance(provider, str)
            and provider in ai_service.DEFAULT_BASE_URLS
            and ai_service.is_loopback_base_url(provider, str(base_url or ""))
        )
        profile["cost_class"] = "local" if local else "paid"
    return stored


def _normalize_cost_classes(merged: dict[str, Any]) -> dict[str, Any]:
    """Never keep "local" next to a remote server URL.

    Local means loopback inference. Saving a remote URL without reclassifying it
    would let the stored value contradict what the request actually reaches, so
    an unclassified remote server is stored as paid and needs approval.
    """
    ai = merged.get("ai")
    if not isinstance(ai, dict):
        return merged
    for task in ai_secrets.TASKS:
        profile = ai.get(task)
        if not isinstance(profile, dict) or profile.get("cost_class") != "local":
            continue
        provider = profile.get("provider", "ollama")
        if not isinstance(provider, str) or provider not in ai_service.DEFAULT_BASE_URLS:
            continue
        if not ai_service.is_loopback_base_url(provider, str(profile.get("base_url") or "")):
            profile["cost_class"] = "paid"
    return merged


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
    stored = _infer_cost_classes(
        _migrate_legacy_ai(copy.deepcopy(row.value or {}))
    )
    merged = _deep_merge(AppSettings().model_dump(), stored)
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
    merged = _normalize_cost_classes(merged)
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
