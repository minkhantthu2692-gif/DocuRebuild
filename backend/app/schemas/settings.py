from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ai import AiProviderKind

ThemeMode = Literal["system", "light", "dark"]
AccentName = Literal["indigo", "violet", "blue", "teal", "emerald", "amber", "rose"]
RadiusStyle = Literal["compact", "soft", "rounded"]
BlurLevel = Literal["off", "subtle", "strong"]
Density = Literal["comfortable", "compact"]
FontSizePreset = Literal["sm", "md", "lg"]
MotionPreference = Literal["full", "reduced"]
LanguageCode = Literal["en", "my", "system"]
DocumentFont = Literal["serif", "sans"]
PdfPageSize = Literal["a4", "letter"]
PdfMargin = Literal["narrow", "normal", "wide"]


class AppearanceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: ThemeMode = "system"
    accent: AccentName = "indigo"
    radius: RadiusStyle = "soft"
    blur: BlurLevel = "subtle"
    density: Density = "comfortable"
    font_size: FontSizePreset = "md"
    motion: MotionPreference = "full"


class AppearancePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: ThemeMode | None = None
    accent: AccentName | None = None
    radius: RadiusStyle | None = None
    blur: BlurLevel | None = None
    density: Density | None = None
    font_size: FontSizePreset | None = None
    motion: MotionPreference | None = None


class EditorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_font: DocumentFont = "serif"


class EditorPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_font: DocumentFont | None = None


class ExportSettings(BaseModel):
    """Local document export preferences. Only PDF uses a layout choice."""

    model_config = ConfigDict(extra="forbid")

    pdf_page_size: PdfPageSize = "a4"
    pdf_margin: PdfMargin = "normal"


class ExportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pdf_page_size: PdfPageSize | None = None
    pdf_margin: PdfMargin | None = None


class BackupSettings(BaseModel):
    """Local backup vault preferences. Automatic copies run only when opted in."""

    model_config = ConfigDict(extra="forbid")

    auto_on_open: bool = False
    # Minimum age of the newest copy before opening a project creates another.
    interval_hours: int = Field(default=24, ge=1, le=24 * 30)
    # Newest copies kept per project, for manual and automatic copies alike.
    keep_copies: int = Field(default=5, ge=1, le=50)


class BackupPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_on_open: bool | None = None
    interval_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    keep_copies: int | None = Field(default=None, ge=1, le=50)


def _validate_base_url(value: str) -> str:
    """Accept an empty value or a credential-free http(s) base URL."""
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        return ""
    if len(cleaned) > 500:
        raise ValueError("Base URL is too long.")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be an http or https URL.")
    if parsed.username or parsed.password:
        raise ValueError("Base URL must not contain credentials.")
    return cleaned


class AiProfileSettings(BaseModel):
    """One AI server profile for a task (text cleanup or image analysis)."""

    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind = "ollama"
    # Empty uses the provider's documented local default.
    base_url: str = ""
    # Empty means no model is chosen, so AI actions stay disabled.
    model: str = Field(default="", max_length=200)
    # Explicit consent for a non-loopback server. Loopback needs no consent.
    allow_remote: bool = False
    # Derived from the encrypted secret store on read; never persisted with the
    # rest of the settings and never returned as the key itself.
    has_api_key: bool = False

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, value: str) -> str:
        return _validate_base_url(value)

    @field_validator("model")
    @classmethod
    def _check_model(cls, value: str) -> str:
        return value.strip()


def _validate_api_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("An API key cannot be empty; omit it or clear the saved key.")
    if len(cleaned) > 1024:
        raise ValueError("The API key is too long.")
    if any(character.isspace() for character in cleaned) or "\x00" in cleaned:
        raise ValueError("An API key must be one line without spaces.")
    if not cleaned.isascii() or not cleaned.isprintable():
        raise ValueError("An API key must use printable ASCII characters.")
    return cleaned


class AiProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind | None = None
    base_url: str | None = None
    model: str | None = Field(default=None, max_length=200)
    allow_remote: bool | None = None
    # Write-only: stored encrypted, never echoed back in any response.
    api_key: str | None = None
    # Explicitly remove the stored key for this task profile.
    clear_api_key: bool | None = None

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, value: str | None) -> str | None:
        return None if value is None else _validate_base_url(value)

    @field_validator("model")
    @classmethod
    def _check_model(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()

    @field_validator("api_key")
    @classmethod
    def _check_api_key(cls, value: str | None) -> str | None:
        return _validate_api_key(value)

    @model_validator(mode="after")
    def _check_key_action(self) -> "AiProfilePatch":
        if self.api_key is not None and self.clear_api_key:
            raise ValueError("Set an API key or clear it, not both.")
        return self


class AiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: AiProfileSettings = Field(default_factory=AiProfileSettings)
    # Image analysis is a separate task profile, so it can use its own local
    # server, model and remote consent. Empty model keeps image AI disabled.
    vision: AiProfileSettings = Field(default_factory=AiProfileSettings)
    # Rolling 24-hour cap for AI request attempts. Zero means unlimited.
    request_limit: int = Field(default=0, ge=0, le=10_000)


class AiPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: AiProfilePatch | None = None
    vision: AiProfilePatch | None = None
    request_limit: int | None = Field(default=None, ge=0, le=10_000)


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: LanguageCode = "en"
    appearance: AppearanceSettings = Field(default_factory=AppearanceSettings)
    editor: EditorSettings = Field(default_factory=EditorSettings)
    export: ExportSettings = Field(default_factory=ExportSettings)
    ai: AiSettings = Field(default_factory=AiSettings)
    backups: BackupSettings = Field(default_factory=BackupSettings)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: LanguageCode | None = None
    appearance: AppearancePatch | None = None
    editor: EditorPatch | None = None
    export: ExportPatch | None = None
    ai: AiPatch | None = None
    backups: BackupPatch | None = None
