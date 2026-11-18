from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ocr import OcrRunOut
from app.schemas.regions import RegionProposalOut

AiProviderKind = Literal["ollama", "openai_compatible"]
AiProbeStatus = Literal[
    "ready",
    "unreachable",
    "timeout",
    "http_error",
    "invalid_response",
]
AiProbeErrorCode = Literal[
    "ai_unreachable",
    "ai_timeout",
    "ai_http_error",
    "ai_invalid_response",
    "ai_rate_limited",
    "ai_auth_failed",
]
AiTask = Literal["ocr_cleanup"]
AiUsageTask = Literal["ocr_cleanup", "region_proposals", "equation_transcription"]
AiTaskProfile = Literal["text", "vision"]
AiSuggestionStatus = Literal["pending", "accepted", "rejected"]
AiUsageOutcome = Literal["success", "error"]


class AiProviderOut(BaseModel):
    id: AiProviderKind
    default_base_url: str


class AiProvidersOut(BaseModel):
    providers: list[AiProviderOut]


class AiProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind
    base_url: str = Field(default="", max_length=500)
    # Required before any request leaves the loopback interface.
    allow_remote: bool = False
    # Write-only override for testing an unsaved key. When omitted, the stored key
    # for `task` is used, so a saved remote profile can be tested again.
    api_key: str | None = Field(default=None, max_length=1024)
    task: AiTaskProfile | None = None


class AiModelOut(BaseModel):
    id: str
    family: str | None = None
    parameter_size: str | None = None


class AiProbeOut(BaseModel):
    status: AiProbeStatus
    provider: AiProviderKind
    base_url: str
    models: list[AiModelOut]
    version: str | None = None
    error_code: AiProbeErrorCode | None = None
    http_status: int | None = None
    # Advisory value from the provider's Retry-After header, capped for display.
    retry_after_seconds: int | None = None


class AiSuggestionCreate(BaseModel):
    """Optional per-request overrides for the saved text profile."""

    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind | None = None
    base_url: str | None = None
    model: str | None = None
    # Must be true before a paid profile is allowed to generate anything.
    confirm_paid: bool = False


class AiSuggestionOut(BaseModel):
    id: str
    page_id: str
    page_number: int | None = None
    block_id: str
    task: AiTask
    original_text: str
    proposed_text: str
    provider: AiProviderKind
    model: str
    base_url: str
    status: AiSuggestionStatus
    created_at: str
    updated_at: str


class AiSuggestionsOut(BaseModel):
    suggestions: list[AiSuggestionOut]


class AiUsageEntryOut(BaseModel):
    id: str
    provider: str
    model: str
    task: str
    outcome: AiUsageOutcome
    error_code: str | None = None
    project_id: str | None = None
    page_id: str | None = None
    block_id: str | None = None
    created_at: str


class AiUsageOut(BaseModel):
    window_hours: int
    request_limit: int
    used: int
    remaining: int | None = None
    successful: int
    failed: int
    recent: list[AiUsageEntryOut]


class AiUsageHistoryEntryOut(AiUsageEntryOut):
    project_name: str | None = None


class AiUsageHistoryOut(BaseModel):
    entries: list[AiUsageHistoryEntryOut]
    total: int
    limit: int
    offset: int


class AiSuggestionDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected"]


class AiSuggestionDecisionOut(BaseModel):
    suggestion: AiSuggestionOut
    run: OcrRunOut


class AiSuggestionBulkIn(BaseModel):
    """Decide several pending proposals at once, with per-proposal revalidation."""

    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=100)
    status: Literal["accepted", "rejected"]


class AiSuggestionBulkItemOut(BaseModel):
    id: str
    status: AiSuggestionStatus | None = None
    error_code: str | None = None


class AiSuggestionBulkOut(BaseModel):
    results: list[AiSuggestionBulkItemOut]
    requested: int
    succeeded: int
    failed: int


class AiRegionProposalsRequest(BaseModel):
    """Optional per-request overrides for the saved vision connection."""

    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind | None = None
    base_url: str | None = None
    model: str | None = None
    # Must be true before a paid profile is allowed to analyse an image.
    confirm_paid: bool = False


class AiRegionProposalsOut(BaseModel):
    status: Literal["ready"]
    page_width: int
    page_height: int
    provider: AiProviderKind
    model: str
    proposals: list[RegionProposalOut]


class AiEquationRequest(BaseModel):
    """Optional per-request overrides for the saved vision connection."""

    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind | None = None
    base_url: str | None = None
    model: str | None = None
    # Must be true before a paid profile is allowed to transcribe a crop.
    confirm_paid: bool = False


class AiEquationOut(BaseModel):
    element_id: str
    page_id: str
    latex: str
    provider: AiProviderKind
    model: str
    base_url: str
