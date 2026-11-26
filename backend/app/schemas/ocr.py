from __future__ import annotations

from pydantic import BaseModel, Field


class OcrCapabilitiesOut(BaseModel):
    engine: str
    available: bool
    version: str | None
    command: str
    tessdata_dir: str | None
    languages: list[str]
    preferred_languages: list[str]
    page_segmentation_mode: int = 3
    page_segmentation_modes: list[int] = Field(default_factory=lambda: [3, 4, 6, 11])
    reason: str | None = None
    setup_hint: str | None = None


class OcrRunRequest(BaseModel):
    languages: list[str] = Field(default_factory=lambda: ["eng"])
    # Optional override of the configured page segmentation mode (3, 4, 6, 11).
    page_segmentation_mode: int | None = None


class OcrBlockUpdate(BaseModel):
    text: str | None = None
    verified: bool | None = None


class OcrLineOut(BaseModel):
    """One visual text line inside a reviewable block.

    Text is always the line text the engine produced; only the geometry comes
    from the stored word boxes. A consumer can therefore reconstruct paragraphs
    without altering the recognised characters.
    """

    text: str
    x: int
    y: int
    width: int
    height: int


class OcrBlockOut(BaseModel):
    id: str
    run_id: str
    page_id: str
    block_index: int
    kind: str
    text: str
    confidence: float | None
    x: int | None
    y: int | None
    width: int | None
    height: int | None
    line_count: int
    word_count: int
    verified: bool
    corrected: bool
    # Empty when word geometry is unavailable or does not line up with the
    # stored text; consumers then fall back to the block box.
    lines: list[OcrLineOut] = Field(default_factory=list)
    created_at: str
    updated_at: str


class OcrRunOut(BaseModel):
    id: str
    page_id: str
    status: str
    engine: str
    engine_version: str | None
    languages: list[str]
    source_asset_id: str | None
    rotation: int
    mean_confidence: float | None
    text: str
    error: str | None
    error_code: str | None
    created_at: str
    updated_at: str
    completed_at: str | None
    stale: bool
    blocks: list[OcrBlockOut]
