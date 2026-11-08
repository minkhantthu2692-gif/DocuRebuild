from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.settings import AppSettings, SettingsUpdate
from app.services.settings import get_app_settings, update_app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
def read_settings(session: DbSession) -> AppSettings:
    return get_app_settings(session)


@router.patch("", response_model=AppSettings)
def patch_settings(payload: SettingsUpdate, session: DbSession) -> AppSettings:
    return update_app_settings(session, payload)
