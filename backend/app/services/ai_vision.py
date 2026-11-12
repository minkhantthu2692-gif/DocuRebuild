from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from app.core.errors import AppError
from app.core.storage import resolve_within
from app.db.project_schema import project_db
from app.schemas.ai import AiProviderKind
from app.schemas.settings import AiProfileSettings
from app.services import ai as ai_service
from app.services.regions import (
    DEDUPE_IOU,
    MAX_PROPOSALS,
    already_extracted,
    clamp_rect,
    iou,
)

# Vision models are sensitive to image size but not to the original resolution.
# A bounded JPEG keeps the request small while preserving enough detail to find
# table, figure and equation boundaries.
MAX_IMAGE_DIM = 1600
IMAGE_QUALITY = 85


def _encode_page_image(path: Path) -> str:
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
    except (OSError, ValueError) as exc:
        raise AppError(
            409,
            "ai_page_image_missing",
            "The page image could not be read for AI analysis.",
        ) from exc
    image.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=IMAGE_QUALITY, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def propose_regions(
    project_dir: Path,
    page_id: str,
    profile: AiProfileSettings,
    vision_model: str,
    *,
    provider: AiProviderKind | None = None,
    base_url: str | None = None,
    model: str | None = None,
    on_attempt: Callable[[ai_service.RequestAttempt], None] | None = None,
) -> dict[str, Any]:
    """Ask the configured vision model for reviewable region proposals.

    Only the current page image is sent, and nothing is saved: the response is
    mapped back to source pixels so the user can inspect, adjust or ignore each
    region before using the normal extraction path.
    """
    with project_db(project_dir) as conn:
        page = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        if page is None:
            raise AppError(404, "page_not_found", "Page not found.")
        width = int(page["width"] or 0)
        height = int(page["height"] or 0)
        if width <= 0 or height <= 0:
            raise AppError(
                409,
                "ai_page_image_missing",
                "This page has no image geometry for AI analysis.",
            )
        asset_id = page["display_asset_id"] or page["original_asset_id"]
        asset = (
            conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if asset_id
            else None
        )
        if asset is None:
            raise AppError(
                409,
                "ai_page_image_missing",
                "The page image could not be read for AI analysis.",
            )
        try:
            image_path = resolve_within(project_dir, asset["relative_path"])
        except ValueError as exc:
            raise AppError(500, "asset_path_invalid", "Asset path is invalid.") from exc
        existing = [
            {
                "x": float(row["x"]),
                "y": float(row["y"]),
                "width": float(row["width"]),
                "height": float(row["height"]),
            }
            for row in conn.execute(
                "SELECT x, y, width, height FROM elements WHERE page_id = ?",
                (page_id,),
            ).fetchall()
        ]

    image_b64 = _encode_page_image(image_path)
    completion = ai_service.request_region_proposals(
        profile,
        image_b64,
        vision_model=vision_model,
        provider=provider,
        base_url=base_url,
        model=model,
        on_attempt=on_attempt,
    )

    proposals: list[dict[str, Any]] = []
    for region in completion.regions:
        rect = clamp_rect(
            {
                "x": region["x"] * width,
                "y": region["y"] * height,
                "width": region["width"] * width,
                "height": region["height"] * height,
            },
            width,
            height,
        )
        if rect is None:
            continue
        proposal = {
            "key": (
                f"ai-{region['kind']}-{rect['x']}-{rect['y']}-"
                f"{rect['width']}-{rect['height']}"
            ),
            "kind": region["kind"],
            "x": rect["x"],
            "y": rect["y"],
            "width": rect["width"],
            "height": rect["height"],
            "caption": region["caption"],
            "reason": "ai_vision",
            "confidence": "low",
            "block_ids": [],
        }
        if any(already_extracted(proposal, element) for element in existing):
            continue
        if any(iou(proposal, kept) >= DEDUPE_IOU for kept in proposals):
            continue
        proposals.append(proposal)
        if len(proposals) >= MAX_PROPOSALS:
            break

    proposals.sort(key=lambda item: (item["y"], item["x"], item["kind"]))
    return {
        "status": "ready",
        "page_width": width,
        "page_height": height,
        "provider": completion.provider,
        "model": completion.model,
        "proposals": proposals,
    }
