from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from platformdirs import user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__


class Settings(BaseSettings):
    """Local runtime configuration.

    Everything is optional. Values can be supplied through environment
    variables prefixed with ``DOCUREBUILD_`` or a local ``.env`` file.
    No remote service is required.
    """

    model_config = SettingsConfigDict(
        env_prefix="DOCUREBUILD_",
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DocuRebuild"
    version: str = __version__
    environment: str = "development"

    data_dir: Path = Field(
        default_factory=lambda: Path(user_data_dir("DocuRebuild", "DocuRebuild"))
    )
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    max_import_mb: int = 200
    max_upload_batch: int = 50
    # Project backups contain every source image, so they can be much larger than
    # a single import. They are read locally and never uploaded anywhere.
    max_backup_mb: int = 2048
    repository_url: str = "https://github.com/minkhantthu2692-gif/DocuRebuild"

    # Local PDF rendering. Pages are rendered one at a time on the backend.
    pdf_render_dpi: int = 150
    pdf_max_pages: int = 1000

    # Local OCR. Nothing here contacts a remote service.
    tesseract_cmd: str = "tesseract"
    tessdata_dir: Path | None = None
    ocr_default_languages: list[str] = ["eng"]
    ocr_timeout_seconds: int = 180
    ocr_max_image_edge: int = 4000
    ocr_max_workers: int = 2
    # Local import worker. Imports are heavy (PDF rendering); keep the pool small
    # so low-end machines are not overloaded.
    import_max_workers: int = 2

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def trash_dir(self) -> Path:
        return self.data_dir / "trash"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_layout(self) -> None:
        for path in (
            self.data_dir,
            self.projects_dir,
            self.trash_dir,
            self.tmp_dir,
            self.backups_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir = settings.data_dir.expanduser().resolve()
    if settings.tessdata_dir is not None:
        settings.tessdata_dir = settings.tessdata_dir.expanduser().resolve()
    settings.ensure_layout()
    return settings
