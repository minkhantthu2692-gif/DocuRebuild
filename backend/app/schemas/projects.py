from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Project name cannot be empty.")
        return cleaned


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Project name cannot be empty.")
        return cleaned


class ProjectSummary(BaseModel):
    id: str
    name: str
    description: str
    page_count: int
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime | None


class ProjectDetail(ProjectSummary):
    directory: str
    document_updated_at: datetime | None


class DocumentPayload(BaseModel):
    content: dict[str, Any]
    plain_text: str = ""

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "doc":
            raise ValueError("Document content must be a Tiptap document node.")
        return value


class DocumentOut(DocumentPayload):
    format: str
    schema_version: int
    updated_at: str | None
