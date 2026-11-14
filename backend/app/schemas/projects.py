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


class DocumentRevisionSummary(BaseModel):
    id: str
    source: str
    preview: str
    character_count: int
    created_at: str


class DocumentRevisionOut(DocumentRevisionSummary):
    content: dict[str, Any]
    plain_text: str


class HistoryEventOut(BaseModel):
    id: str
    event_type: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ProjectBackupSummary(BaseModel):
    filename: str
    byte_size: int
    created_at: str


class EncryptedBackupRequest(BaseModel):
    """Password for a one-off encrypted backup download.

    The value is used to derive a key for this response only; it is never stored.
    Length is validated in the service so the error carries a stable code.
    """

    password: str


class BackupPageSummary(BaseModel):
    id: str
    page_number: int
    source_kind: str
    status: str
    width: int | None = None
    height: int | None = None
    original_filename: str | None = None


class BackupSelectionOut(BaseModel):
    """Pages found in an inspected archive, keyed by a short-lived token."""

    token: str
    source_name: str
    created_at: str
    pages: list[BackupPageSummary]


class PageRestoreRequest(BaseModel):
    page_ids: list[str]


class PageRestoreOut(BaseModel):
    restored: int
    page_numbers: list[int]
