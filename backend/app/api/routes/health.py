from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.api.deps import DbSession
from app.core.config import get_settings
from app.db.models import Project
from app.schemas.meta import AppCapabilities, AppMeta, HealthStatus
from app.services import ocr as ocr_service
from app.services import pdf as pdf_service

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthStatus)
def health(session: DbSession) -> HealthStatus:
    database = "ok"
    try:
        session.execute(text("SELECT 1"))
        projects = session.scalar(select(func.count()).select_from(Project)) or 0
    except Exception:
        database = "error"
        projects = 0
    settings = get_settings()
    return HealthStatus(
        status="ok" if database == "ok" else "degraded",
        version=settings.version,
        database=database,
        data_dir=str(settings.data_dir),
        projects=int(projects),
    )


@router.get("/meta", response_model=AppMeta)
def meta() -> AppMeta:
    settings = get_settings()
    return AppMeta(
        name=settings.app_name,
        version=settings.version,
        capabilities=AppCapabilities(
            import_images=True,
            import_pdf=pdf_service.pdf_available(),
            image_transform=True,
            element_extraction=True,
            region_proposals=True,
            ocr=ocr_service.engine_available(),
            # The local AI adapter and review workflow exist, but a user must
            # configure and test a local server and model before using it.
            ai=True,
            export=False,
        ),
        max_import_mb=settings.max_import_mb,
        max_upload_batch=settings.max_upload_batch,
        repository_url=settings.repository_url or None,
    )
