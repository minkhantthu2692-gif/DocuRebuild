from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

FontSource = Literal["system", "imported"]
FontFamilySource = Literal["system", "imported", "mixed"]


class FontFaceSummary(BaseModel):
    """One usable face. Imported faces have an id and a stored file."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    family: str
    style: str
    weight: int
    italic: bool
    source: FontSource
    format: str
    file_name: str | None = None


class FontFamilySummary(BaseModel):
    """A family grouped from one or more detected or imported faces."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: FontFamilySource
    faces: list[FontFaceSummary]
    # False when a document refers to this name but no font file is available.
    available: bool = True


class FontsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    families: list[FontFamilySummary]
    imported_count: int
    system_count: int
    system_directories: list[str]
