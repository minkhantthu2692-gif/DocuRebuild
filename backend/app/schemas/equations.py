from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

EquationProposalStatus = Literal[
    "ready",
    "no_ocr_run",
    "ocr_not_ready",
    "ocr_failed",
    "ocr_stale",
    "no_geometry",
]


class PageEquationProposalOut(BaseModel):
    """One equation region read from the latest OCR layout.

    The text is unverified OCR output and ``latex`` is that text normalised into
    a LaTeX starting point from the stored word boxes. Neither becomes document
    content until the user reviews the rendered preview.
    """

    key: str
    x: int
    y: int
    width: int
    height: int
    text: str
    latex: str
    display: bool
    confidence: Literal["high", "medium", "low"]
    reason: Literal["equation_text"]
    block_ids: list[str]
    reading_index: int


class PageEquationProposalsOut(BaseModel):
    status: EquationProposalStatus
    page_id: str
    page_width: int | None
    page_height: int | None
    ocr_run_id: str | None
    engine: str | None
    proposals: list[PageEquationProposalOut]
