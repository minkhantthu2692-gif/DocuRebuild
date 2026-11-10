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
ProposalReason = Literal["table_text_grid", "equation_text", "figure_caption_gap"]


class RegionProposalOut(BaseModel):
    key: str
    kind: str
    x: int
    y: int
    width: int
    height: int
    caption: str
    reason: ProposalReason
    confidence: Literal["high", "medium"]
    block_ids: list[str]


class RegionProposalsOut(BaseModel):
    status: ProposalStatus
    page_width: int | None
    page_height: int | None
    ocr_run_id: str | None
    engine: str | None
    proposals: list[RegionProposalOut]
