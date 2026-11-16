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


class TableProposalOut(BaseModel):
    page_id: str
    block_id: str
    run_id: str
    engine: str
    rows: int
    columns: int
    has_confidence: bool
    uncertain_cells: int
    empty_cells: int
    warnings: list[TableWarning]
    cells: list[TableCellOut]
