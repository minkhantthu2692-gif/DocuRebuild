from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ImportJobStatus = Literal[
    "queued",
    "running",
    "cancelling",
    "succeeded",
    "failed",
    "cancelled",
]


class ImportJobOut(BaseModel):
    id: str
    kind: str
    status: ImportJobStatus
    progress: float
    total_pages: int
    imported_pages: int
    current_file: str | None
    file_count: int
    filenames: list[str]
    error: str | None
    error_code: str | None
    created_at: str
    updated_at: str
    completed_at: str | None
