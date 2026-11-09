from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PageOut(BaseModel):
    id: str
    page_number: int
    source_kind: str
    status: str
    width: int | None
    height: int | None
    original_asset_id: str | None
    display_asset_id: str | None
    thumbnail_asset_id: str | None
    original_filename: str | None
    rotation: int
    pdf_page_number: int | None = None
    created_at: str
    updated_at: str


class RotateRequest(BaseModel):
    degrees: int = 90

    @field_validator("degrees")
    @classmethod
    def _validate_degrees(cls, value: int) -> int:
        if value % 90 != 0 or not -360 <= value <= 360:
            raise ValueError("Rotation must be a multiple of 90 degrees.")
        return value


class ReorderRequest(BaseModel):
    page_ids: list[str] = Field(default_factory=list)
