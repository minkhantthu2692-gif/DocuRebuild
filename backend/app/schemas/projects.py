from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


def _clean_layout_text(value: str) -> str:
    """Collapse whitespace so a header/footer stays on one line."""
    cleaned = " ".join(value.split())
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        raise ValueError(
            "Page header and footer text contains an unsupported control character."
        )
    return cleaned


class DocumentLayoutUpdate(BaseModel):
    """Plain header/footer text for paginated exports.

    ``{page}``, ``{pages}`` and ``{title}`` are the only recognized tokens.
    Unknown braces are kept literally, so the text is never silently rewritten.
    """

    header_text: str = Field(default="", max_length=200)
    footer_text: str = Field(default="", max_length=200)
    show_page_numbers: bool = True

    @field_validator("header_text", "footer_text", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return _clean_layout_text(value)


class DocumentLayoutOut(DocumentLayoutUpdate):
    updated_at: str


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
    # Whether this page still exists in the inspecting project, and which of its
    # image slots are missing there. ``restorable_slots`` is the subset the
    # backup can supply, so the dialog can offer a repair only when it can work.
    in_project: bool = False
    missing_slots: list[str] = Field(default_factory=list)
    restorable_slots: list[str] = Field(default_factory=list)


class BackupElementSummary(BaseModel):
    """One extracted region in the backup whose crop is missing here."""

    id: str
    page_id: str
    page_number: int
    kind: str
    caption: str
    verified: bool
    # Whether the backup can supply the crop file, so the dialog offers only
    # repairs that can succeed.
    restorable: bool


class BackupDocumentSummary(BaseModel):
    """The live document stored in a backup, without its full content."""

    preview: str
    character_count: int
    updated_at: str | None = None


class BackupDocumentRevision(BaseModel):
    """One stored document version found in a backup."""

    id: str
    source: str
    preview: str
    character_count: int
    created_at: str


class BackupDocumentOut(BaseModel):
    current: BackupDocumentSummary
    revisions: list[BackupDocumentRevision]


class BackupSelectionOut(BaseModel):
    """Pages, damaged region crops and document versions in an inspected archive."""

    token: str
    source_name: str
    created_at: str
    pages: list[BackupPageSummary]
    elements: list[BackupElementSummary]
    # True when more damaged regions exist than one inspection lists.
    elements_truncated: bool = False
    document: BackupDocumentOut


class PageRestoreRequest(BaseModel):
    page_ids: list[str]


class PageRestoreOut(BaseModel):
    restored: int
    page_numbers: list[int]


class PageAssetRepairRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=64)


class PageAssetRepairOut(BaseModel):
    page_id: str
    page_number: int
    restored_slots: list[str]


class ElementAssetRepairRequest(BaseModel):
    element_id: str = Field(min_length=1, max_length=64)


class ElementAssetRepairOut(BaseModel):
    element_id: str
    page_id: str
    page_number: int
    kind: str
    restored: bool


class DocumentRestoreRequest(BaseModel):
    """``revision_id=None`` restores the backup's live document."""

    revision_id: str | None = Field(default=None, min_length=1, max_length=64)


class DocumentRestoreOut(BaseModel):
    restored: bool
    source: Literal["current", "revision"]
    revision_id: str | None = None
    updated_at: str | None = None
    document: DocumentOut


class ProjectBulkDeleteRequest(BaseModel):
    project_ids: list[str] = Field(min_length=1, max_length=500)


class ProjectBulkDeleteFailure(BaseModel):
    id: str
    code: str
    message: str


class ProjectBulkDeleteResult(BaseModel):
    deleted: list[str] = Field(default_factory=list)
    failed: list[ProjectBulkDeleteFailure] = Field(default_factory=list)
    trash_paths: list[str] = Field(default_factory=list)
