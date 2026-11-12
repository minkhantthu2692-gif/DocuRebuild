from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    """One local AI server profile for a task profile (text for now)."""

    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind = "ollama"
    # Empty uses the provider's documented local default.
    base_url: str = ""
    # Empty means no model is chosen, so AI actions stay disabled.
    model: str = Field(default="", max_length=200)
    # Explicit consent for a non-loopback server. Loopback needs no consent.
    allow_remote: bool = False

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, value: str) -> str:
        return _validate_base_url(value)

    @field_validator("model")
    @classmethod
    def _check_model(cls, value: str) -> str:
        return value.strip()


class AiProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind | None = None
    base_url: str | None = None
    model: str | None = Field(default=None, max_length=200)
    allow_remote: bool | None = None

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, value: str | None) -> str | None:
        return None if value is None else _validate_base_url(value)

    @field_validator("model")
    @classmethod
    def _check_model(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()


class AiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: AiProfileSettings = Field(default_factory=AiProfileSettings)
    # Model used for page-image region proposals. Empty keeps image AI disabled.
    vision_model: str = Field(default="", max_length=200)
    # Rolling 24-hour cap for AI request attempts. Zero means unlimited.
    request_limit: int = Field(default=0, ge=0, le=10_000)

    @field_validator("vision_model")
    @classmethod
    def _check_vision_model(cls, value: str) -> str:
        return value.strip()


class AiPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: AiProfilePatch | None = None
    vision_model: str | None = Field(default=None, max_length=200)
    request_limit: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("vision_model")
    @classmethod
    def _check_vision_model(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: LanguageCode = "en"
    appearance: AppearanceSettings = Field(default_factory=AppearanceSettings)
    editor: EditorSettings = Field(default_factory=EditorSettings)
    ai: AiSettings = Field(default_factory=AiSettings)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: LanguageCode | None = None
    appearance: AppearancePatch | None = None
    editor: EditorPatch | None = None
    ai: AiPatch | None = None
