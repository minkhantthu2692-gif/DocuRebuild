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


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: LanguageCode = "en"
    appearance: AppearanceSettings = Field(default_factory=AppearanceSettings)
    editor: EditorSettings = Field(default_factory=EditorSettings)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: LanguageCode | None = None
    appearance: AppearancePatch | None = None
    editor: EditorPatch | None = None
