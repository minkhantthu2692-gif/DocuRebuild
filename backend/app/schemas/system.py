from __future__ import annotations

from pydantic import BaseModel, Field


class FactoryResetRequest(BaseModel):
    """The exact word the user must type before local data is erased."""

    confirm: str = Field(min_length=1, max_length=32)


class FactoryResetResult(BaseModel):
    ok: bool
    data_dir: str
    projects_removed: int
