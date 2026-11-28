from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TableWarning = Literal["no_confidence", "low_confidence", "empty_cells"]
TableAlignment = Literal["left", "center", "right"]


class TableCellOut(BaseModel):
    row: int
    column: int
    text: str
    confidence: float | None
    uncertain: bool
    empty: bool
    alignment: TableAlignment | None = None
    # A merged cell is anchored at `row`/`column`; the covered coordinates are
    # not repeated as cells. Both stay 1 for a plain grid.
    rowspan: int = 1
    colspan: int = 1


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


class TableNestedOut(BaseModel):
    """A child grid sits inside one cell of the parent candidate."""

    parent_key: str
    parent_row: int
    parent_column: int


class TableCandidateOut(BaseModel):
    key: str
    block_ids: list[str]
    rows: int
    columns: int
    has_confidence: bool
    uncertain_cells: int
    empty_cells: int
    warnings: list[TableWarning]
    source: TableSourceOut
    cells: list[TableCellOut]
    nested: TableNestedOut | None = None
    nested_count: int = 0


class PageTableProposalsOut(BaseModel):
    page_id: str
    run_id: str
    engine: str
    page_width: int | None
    page_height: int | None
    candidates: list[TableCandidateOut]


class ElementTableProposalOut(BaseModel):
    """A grid read locally from one saved table crop."""

    element_id: str
    page_id: str
    engine: str
    engine_version: str | None
    languages: list[str]
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
