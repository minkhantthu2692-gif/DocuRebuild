from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ocr import OcrRunOut
from app.schemas.regions import RegionProposalOut
from app.schemas.tables import TableCellOut, TableSourceOut, TableWarning

AiCostClass = Literal["local", "free", "paid"]
AiRotationStrategy = Literal[
    "priority", "failover", "round_robin", "least_recent", "least_usage"
]
AiConnectionStatus = Literal[
    "connected",
    "untested",
    "configuration_required",
    "auth_failed",
    "rate_limited",
    "quota_exhausted",
    "unavailable",
    "error",
    "disabled",
]
AiKeyStatus = Literal["ready", "disabled", "auth_failed", "rate_limited", "error"]
AiTaskCapability = Literal["text", "vision"]
AiUsageTask = Literal[
    "ocr_cleanup", "region_proposals", "equation_transcription", "table_structure"
]
AiSuggestionStatus = Literal["pending", "accepted", "rejected"]
AiUsageOutcome = Literal["success", "error"]
AiTask = Literal["ocr_cleanup"]


class AiProviderOut(BaseModel):
    id: str
    name: str
    kind: str
    default_base_url: str
    requires_base_url: bool
    supports_model_discovery: bool
    allows_manual_models: bool
    local_default: bool
    requires_api_key: bool
    docs_url: str | None = None


class AiProvidersOut(BaseModel):
    providers: list[AiProviderOut]


class AiKeyOut(BaseModel):
    id: str
    label: str
    enabled: bool
    priority: int
    request_limit: int
    auth_failed: bool
    status: AiKeyStatus
    has_secret: bool
    last_used_at: str | None = None
    last_success_at: str | None = None
    last_error_at: str | None = None
    last_error_code: str | None = None
    cooldown_until: str | None = None
    created_at: str | None = None


class AiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="", max_length=80)
    # Write-only. Never echoed back in any response.
    api_key: str = Field(min_length=1, max_length=1024)
    priority: int = Field(default=100, ge=0, le=10_000)
    enabled: bool = True
    request_limit: int = Field(default=0, ge=0, le=100_000)


class AiKeyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=80)
    priority: int | None = Field(default=None, ge=0, le=10_000)
    enabled: bool | None = None
    request_limit: int | None = Field(default=None, ge=0, le=100_000)
    # Explicitly clear an authentication-failure flag after the key is fixed.
    auth_failed: bool | None = None


class AiModelOut(BaseModel):
    id: str
    connection_id: str
    model_id: str
    display_name: str | None = None
    family: str | None = None
    context_window: int | None = None
    input_modalities: list[str] | None = None
    output_modalities: list[str] | None = None
    supports_tools: bool | None = None
    supports_streaming: bool | None = None
    pricing: dict | None = None
    metadata: dict | None = None
    source: Literal["discovered", "manual"]
    available: bool
    favorite: bool = False
    last_used_at: str | None = None
    discovered_at: str | None = None


class AiModelManualCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    context_window: int | None = Field(default=None, ge=1)
    input_modalities: list[str] | None = None
    output_modalities: list[str] | None = None


class AiModelFavoriteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=200)
    favorite: bool


class AiConnectionOut(BaseModel):
    id: str
    provider: str
    provider_name: str
    provider_kind: str
    name: str
    base_url: str
    allow_remote: bool
    cost_class: AiCostClass
    enabled: bool
    rotation_strategy: AiRotationStrategy
    max_attempts: int
    request_limit: int
    monthly_budget_usd: float | None = None
    settings: dict = Field(default_factory=dict)
    status: AiConnectionStatus
    last_error_code: str | None = None
    last_http_status: int | None = None
    retry_after_seconds: int | None = None
    last_checked_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    key_count: int
    enabled_key_count: int
    model_count: int
    requires_api_key: bool


class AiConnectionDetailOut(AiConnectionOut):
    keys: list[AiKeyOut] = Field(default_factory=list)


class AiConnectionsOut(BaseModel):
    connections: list[AiConnectionOut]


class AiConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=120)
    base_url: str = Field(default="", max_length=500)
    allow_remote: bool = False
    cost_class: AiCostClass = "local"
    enabled: bool = True
    rotation_strategy: AiRotationStrategy = "priority"
    max_attempts: int = Field(default=2, ge=1, le=10)
    request_limit: int = Field(default=0, ge=0, le=100_000)
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)


class AiConnectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    allow_remote: bool | None = None
    cost_class: AiCostClass | None = None
    enabled: bool | None = None
    rotation_strategy: AiRotationStrategy | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    request_limit: int | None = Field(default=None, ge=0, le=100_000)
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)


class AiConnectionTestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Write-only unsaved key supplied only for this test.
    api_key: str | None = Field(default=None, max_length=1024)


class AiConnectionTestOut(BaseModel):
    connection_id: str
    status: AiConnectionStatus
    provider: str
    base_url: str
    models_found: int = 0
    cached: bool = False
    version: str | None = None
    error_code: str | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None
    last_checked_at: str | None = None
    message: str | None = None


class AiRouteOut(BaseModel):
    task: str
    connection_id: str | None = None
    connection_name: str | None = None
    connection_status: str | None = None
    cost_class: AiCostClass | None = None
    model_id: str | None = None
    model_display_name: str | None = None
    model_source: str | None = None
    capability: AiTaskCapability
    fallback_connection_id: str | None = None
    fallback_connection_name: str | None = None
    fallback_model_id: str | None = None
    temperature: float
    timeout_seconds: int
    request_limit: int
    configured: bool
    warnings: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class AiRoutesOut(BaseModel):
    routes: list[AiRouteOut]
    default_model: str | None = None


class AiRouteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str | None = None
    model_id: str | None = Field(default=None, max_length=200)
    fallback_connection_id: str | None = None
    fallback_model_id: str | None = Field(default=None, max_length=200)
    temperature: float = Field(default=0.0, ge=0, le=2)
    timeout_seconds: int = Field(default=60, ge=5, le=600)
    request_limit: int = Field(default=0, ge=0, le=100_000)


class AiPreferencesOut(BaseModel):
    daily_request_limit: int
    monthly_budget_usd: float | None = None


class AiPreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_request_limit: int | None = Field(default=None, ge=0, le=100_000)
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)


class AiOverviewOut(BaseModel):
    connection_count: int
    enabled_connection_count: int
    key_count: int
    model_count: int
    configured_task_count: int
    task_count: int
    preferences: AiPreferencesOut


class AiSuggestionCreate(BaseModel):
    """A cleanup request through the routed OCR task."""

    model_config = ConfigDict(extra="forbid")

    # Must be true before a paid connection is allowed to generate anything.
    confirm_paid: bool = False


class AiSuggestionOut(BaseModel):
    id: str
    page_id: str
    page_number: int | None = None
    block_id: str
    task: AiTask
    original_text: str
    proposed_text: str
    provider: str
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
    connection_id: str | None = None
    connection_name: str | None = None
    key_id: str | None = None
    key_label: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    cost_source: str | None = None
    duration_ms: int | None = None
    created_at: str


class AiUsageTaskCountOut(BaseModel):
    """Attempts for one task inside the rolling window, including errors."""

    task: str
    used: int


class AiUsageConnectionCountOut(BaseModel):
    connection_id: str
    connection_name: str
    provider: str
    used: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    unpriced_requests: int


class AiUsageOut(BaseModel):
    window_hours: int
    request_limit: int
    used: int
    remaining: int | None = None
    successful: int
    failed: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    unpriced_requests: int
    monthly_cost_usd: float
    by_task: list[AiUsageTaskCountOut]
    by_connection: list[AiUsageConnectionCountOut]
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
    model_config = ConfigDict(extra="forbid")

    confirm_paid: bool = False


class AiRegionProposalsOut(BaseModel):
    status: Literal["ready"]
    page_width: int
    page_height: int
    provider: str
    model: str
    proposals: list[RegionProposalOut]


class AiEquationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_paid: bool = False


class AiEquationOut(BaseModel):
    element_id: str
    page_id: str
    latex: str
    provider: str
    model: str
    base_url: str


class AiTableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_paid: bool = False


class AiTableOut(BaseModel):
    """A model-read table grid, shaped for the same review dialog as local grids."""

    element_id: str
    page_id: str
    provider: str
    model: str
    base_url: str
    page_width: int | None = None
    page_height: int | None = None
    rows: int
    columns: int
    uncertain_cells: int
    empty_cells: int
    warnings: list[TableWarning]
    source: TableSourceOut
    cells: list[TableCellOut]
