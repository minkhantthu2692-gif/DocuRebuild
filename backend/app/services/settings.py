from __future__ import annotations

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


def get_app_settings(session: Session) -> AppSettings:
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        return AppSettings()
    merged = _deep_merge(AppSettings().model_dump(), row.value or {})
    try:
        return AppSettings.model_validate(merged)
    except ValidationError:
        logger.warning("Stored settings were invalid; falling back to defaults.")
        return AppSettings()


def update_app_settings(session: Session, patch: SettingsUpdate) -> AppSettings:
    current = get_app_settings(session)
    merged = _deep_merge(
        current.model_dump(),
        patch.model_dump(exclude_none=True, exclude_unset=True),
    )
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
