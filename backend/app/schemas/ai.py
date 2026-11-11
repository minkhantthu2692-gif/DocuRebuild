from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.ocr import OcrRunOut

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
]
AiTask = Literal["ocr_cleanup"]
AiSuggestionStatus = Literal["pending", "accepted", "rejected"]


class AiProviderOut(BaseModel):
    id: AiProviderKind
    default_base_url: str


class AiProvidersOut(BaseModel):
    providers: list[AiProviderOut]


class AiProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind
    base_url: str = ""
    # Required before any request leaves the loopback interface.
    allow_remote: bool = False


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


class AiSuggestionCreate(BaseModel):
    """Optional per-request overrides for the saved text profile."""

    model_config = ConfigDict(extra="forbid")

    provider: AiProviderKind | None = None
    base_url: str | None = None
    model: str | None = None


class AiSuggestionOut(BaseModel):
    id: str
    page_id: str
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


class AiSuggestionDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected"]


class AiSuggestionDecisionOut(BaseModel):
    suggestion: AiSuggestionOut
    run: OcrRunOut
