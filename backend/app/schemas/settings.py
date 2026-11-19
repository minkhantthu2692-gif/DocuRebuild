from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class AppSettings(BaseModel):
    """Non-AI application preferences.

    AI connections, task routes, usage limits and privacy settings are managed
    by the BYOK service and its own endpoints, not in this JSON blob.
    """

    model_config = ConfigDict(extra="forbid")

    language: LanguageCode = "en"
    appearance: AppearanceSettings = Field(default_factory=AppearanceSettings)
    editor: EditorSettings = Field(default_factory=EditorSettings)
    export: ExportSettings = Field(default_factory=ExportSettings)
    backups: BackupSettings = Field(default_factory=BackupSettings)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: LanguageCode | None = None
    appearance: AppearancePatch | None = None
    editor: EditorPatch | None = None
    export: ExportPatch | None = None
    backups: BackupPatch | None = None
