from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TableWarning = Literal["no_confidence", "low_confidence", "empty_cells"]


class TableCellOut(BaseModel):
    row: int
    column: int
    text: str
    confidence: float | None
    uncertain: bool
    empty: bool


class TableSourceOut(BaseModel):
    """Pixel region the proposal was read from, in OCR image coordinates."""

    x: float
    y: float
    width: float
    height: float


class TableProposalOut(BaseModel):
    page_id: str
    block_id: str
    run_id: str
    engine: str
    page_width: int | None
    page_height: int | None
    rows: int
    columns: int
    has_confidence: bool
    uncertain_cells: int
    empty_cells: int
    warnings: list[TableWarning]
    source: TableSourceOut
    cells: list[TableCellOut]


class TableCandidateOut(BaseModel):
    block_ids: list[str]
    rows: int
    columns: int
    has_confidence: bool
    uncertain_cells: int
    empty_cells: int
    warnings: list[TableWarning]
    source: TableSourceOut
    cells: list[TableCellOut]


class PageTableProposalsOut(BaseModel):
    page_id: str
    run_id: str
    engine: str
    page_width: int | None
    page_height: int | None
    candidates: list[TableCandidateOut]
