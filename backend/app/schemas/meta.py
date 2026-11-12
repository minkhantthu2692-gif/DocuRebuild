from __future__ import annotations

from pydantic import BaseModel


class AppCapabilities(BaseModel):
    import_images: bool
    import_pdf: bool
    image_transform: bool
    element_extraction: bool
    region_proposals: bool
    ocr: bool
    ai: bool
    export: bool
    backup: bool


class AppMeta(BaseModel):
    name: str
    version: str
    capabilities: AppCapabilities
    max_import_mb: int
    max_upload_batch: int
    max_backup_mb: int = 2048
    repository_url: str | None = None


class HealthStatus(BaseModel):
    status: str
    version: str
    database: str
    data_dir: str
    projects: int
