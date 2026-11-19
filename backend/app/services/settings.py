from __future__ import annotations

import copy
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AppSetting, utcnow
from app.schemas.settings import AppSettings, SettingsUpdate

logger = logging.getLogger(__name__)

SETTINGS_KEY = "app"


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        elif value is not None:
            merged[key] = value
    return merged


def _strip_legacy_ai(stored: dict[str, Any]) -> dict[str, Any]:
    """Remove the pre-BYOK AI blob before validating application settings.

    The BYOK migration backs the old value up under its own key and converts it
    to provider connections. Keeping it out of ``AppSettings`` guarantees the
    legacy configuration is not still driving behavior while that runs.
    """
    stored.pop("ai", None)
    stored.pop("vision_model", None)
    return stored


def get_app_settings(session: Session) -> AppSettings:
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        return AppSettings()
    stored = _strip_legacy_ai(copy.deepcopy(row.value or {}))
    merged = _deep_merge(AppSettings().model_dump(), stored)
    try:
        return AppSettings.model_validate(merged)
    except ValidationError:
        logger.warning("Stored settings were invalid; falling back to defaults.")
        return AppSettings()


def update_app_settings(session: Session, patch: SettingsUpdate) -> AppSettings:
    current = get_app_settings(session)
    patch_values = patch.model_dump(exclude_none=True, exclude_unset=True)
    merged = _deep_merge(current.model_dump(), patch_values)
    try:
        validated = AppSettings.model_validate(merged)
    except ValidationError as exc:
        raise AppError(422, "invalid_settings", "Settings values are not valid.") from exc

    row = session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        row = AppSetting(key=SETTINGS_KEY, value=validated.model_dump(), updated_at=utcnow())
        session.add(row)
    else:
        row.value = validated.model_dump()
        row.updated_at = utcnow()
    session.commit()
    return validated
