from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ElementCreate(BaseModel):
    kind: Literal["figure", "table", "equation"] = "figure"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    caption: str = Field(default="", max_length=500)


class ElementUpdate(BaseModel):
    caption: str | None = Field(default=None, max_length=500)
    verified: bool | None = None


class ElementOut(BaseModel):
    id: str
    page_id: str
    kind: str
    asset_id: str | None
    x: int
    y: int
    width: int
    height: int
    caption: str
    source: str
    verified: bool
    stale: bool
    created_at: str
    updated_at: str
