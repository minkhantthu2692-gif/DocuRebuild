from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ProposalStatus = Literal[
    "ready",
    "no_ocr_run",
    "ocr_not_ready",
    "ocr_failed",
    "ocr_stale",
    "no_geometry",
]
ProposalReason = Literal[
    "table_text_grid",
    "equation_text",
    "figure_caption_gap",
    "pdf_image_region",
    "pdf_drawing_region",
    "page_artwork_region",
    "ai_vision",
]


class RegionProposalOut(BaseModel):
    key: str
    kind: str
    x: int
    y: int
    width: int
    height: int
    caption: str
    reason: ProposalReason
    confidence: Literal["high", "medium", "low"]
    block_ids: list[str]


class RegionProposalsOut(BaseModel):
    status: ProposalStatus
    page_width: int | None
    page_height: int | None
    ocr_run_id: str | None
    engine: str | None
    proposals: list[RegionProposalOut]


class PageRegionProposalsOut(BaseModel):
    page_id: str
    page_number: int
    status: ProposalStatus
    page_width: int | None
    page_height: int | None
    ocr_run_id: str | None
    engine: str | None
    proposal_count: int
    proposals: list[RegionProposalOut]


class ProjectRegionProposalsOut(BaseModel):
    pages: list[PageRegionProposalsOut]
    total_proposals: int
    pages_with_proposals: int
    truncated: bool
    next_page_number: int | None
