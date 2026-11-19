from __future__ import annotations

import json
import logging
import math
import uuid
from pathlib import Path
from typing import Any, Callable, NamedTuple

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.project_schema import project_db, utc_iso
from app.schemas.ai import AiSuggestionStatus
from app.services import ai_router
from app.services import ocr as ocr_service
from app.services.table_structure import (
    MAX_CELLS as MAX_TABLE_CELLS,
    MAX_COLUMNS as MAX_TABLE_COLUMNS,
    MAX_ROWS as MAX_TABLE_ROWS,
    MIN_COLUMNS as MIN_TABLE_COLUMNS,
    MIN_ROWS as MIN_TABLE_ROWS,
)

MAX_TEXT_LENGTH = 20_000

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You correct OCR text for a document reconstruction tool. "
    "Return only the corrected text and nothing else. "
    "Do not translate, summarize, explain, reorder or add content. "
    "Preserve line breaks, punctuation, numbers and the original language. "
    "If a character is genuinely unreadable, keep the original character."
)

VISION_PROMPT = (
    "You analyse one scanned document page image for a document reconstruction tool. "
    'Return only a JSON object and nothing else, shaped like {"regions": ['
    '{"kind": "figure|table|equation", "x": 0.0, "y": 0.0, "width": 0.0, '
    '"height": 0.0, "caption": ""}]}. '
    "x, y, width and height are fractions of the page image measured from the "
    "top-left corner and must be between 0 and 1. "
    "Include only figures, tables and equations that are clearly visible. "
    "Use caption for a printed caption or label that belongs to the region, "
    "otherwise use an empty string. "
    "Do not include ordinary text paragraphs, headers, footers or page numbers. "
    "Do not invent regions. Return an empty regions array when nothing is visible."
)

MAX_VISION_REGIONS = 12
MIN_VISION_REGION_SIDE = 0.02
VISION_REGION_KINDS = frozenset({"figure", "table", "equation"})

EQUATION_PROMPT = (
    "You transcribe one mathematical equation from a document image crop for a "
    "reconstruction tool. Return only the LaTeX that typesets exactly the equation "
    "that is visible: no prose, no code fence, no delimiters and no explanation. "
    "Never add symbols, terms or numbers that are not clearly visible, and never "
    "simplify or solve the equation. If no equation can be read, return an empty "
    "string."
)
MAX_EQUATION_LENGTH = 4_000

# A model reply is a proposal, not a source of truth. These caps mirror the
# deterministic table proposal so a model cannot produce a grid the review dialog
# and editor reject; an oversized reply is refused rather than truncated.
TABLE_PROMPT = (
    "You transcribe one table from a document image crop for a reconstruction tool. "
    'Return only a JSON object and nothing else, shaped like {"rows": ['
    '["cell", "cell"], ["cell", "cell"]]}. '
    "Every row must contain the same number of cells. "
    "Transcribe only text that is clearly visible, keep the original language and "
    "punctuation, and use an empty string for a cell with no text. "
    "Do not merge or split cells, do not add a header, and never invent, guess or "
    "complete missing text. "
    'Return {"rows": []} when no table can be read.'
)
MAX_TABLE_CELL_LENGTH = 2_000


class Completion(NamedTuple):
    text: str
    provider: str
    model: str
    base_url: str


class VisionCompletion(NamedTuple):
    """Validated, normalized regions proposed from one page image."""

    regions: list[dict[str, Any]]
    provider: str
    model: str
    base_url: str


class EquationCompletion(NamedTuple):
    """LaTeX proposed for one equation crop, still unverified."""

    latex: str
    provider: str
    model: str
    base_url: str


class TableCompletion(NamedTuple):
    """A rectangular text grid proposed for one table crop, still unverified."""

    rows: list[list[str]]
    provider: str
    model: str
    base_url: str


def _run_routed(
    session: Session,
    task: str,
    *,
    system_prompt: str,
    user_text: str,
    image_b64: str | None = None,
    project_id: str | None = None,
    page_id: str | None = None,
    block_id: str | None = None,
    confirm_paid: bool = False,
    json_mode: bool = False,
    validator=None,
):
    """Send one request through the single BYOK task router."""
    return ai_router.complete(
        session,
        task,
        system_prompt=system_prompt,
        user_text=user_text,
        image_b64=image_b64,
        project_id=project_id,
        page_id=page_id,
        block_id=block_id,
        confirm_paid=confirm_paid,
        json_mode=json_mode,
        validator=validator,
    )


def _strip_code_fence(value: str) -> str:
    if not value.startswith("```"):
        return value
    lines = value.splitlines()
    if len(lines) < 2:
        return value
    if lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines[1:]).strip()


def parse_region_proposals(content: str) -> list[dict[str, Any]]:
    """Validate the model's normalized regions and drop anything unusable.

    The model is free to return extra prose, wrong kinds or out-of-page boxes;
    only bounded, finite rectangles of a supported kind become proposals.
    """
    payload = _strip_code_fence(content.strip())
    try:
        body = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AppError(
            502,
            "ai_invalid_response",
            "The AI region proposal was not valid JSON.",
        ) from exc
    raw = body.get("regions") if isinstance(body, dict) else body
    if not isinstance(raw, list):
        raise AppError(
            502,
            "ai_invalid_response",
            "The AI region proposal had an unexpected shape.",
        )

    regions: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        kind = kind.strip().lower() if isinstance(kind, str) else ""
        if kind not in VISION_REGION_KINDS:
            continue
        values: list[float] = []
        for key in ("x", "y", "width", "height"):
            value = item.get(key)
            # bool is an int subclass and would silently become 0 or 1.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                values = []
                break
            number = float(value)
            if not math.isfinite(number):
                values = []
                break
            values.append(number)
        if len(values) != 4:
            continue
        x, y, width, height = values
        if x < 0 or y < 0 or x >= 1 or y >= 1 or width <= 0 or height <= 0:
            continue
        width = min(width, 1 - x)
        height = min(height, 1 - y)
        if width < MIN_VISION_REGION_SIDE or height < MIN_VISION_REGION_SIDE:
            continue
        caption = item.get("caption")
        regions.append(
            {
                "kind": kind,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "caption": caption.strip()[:500] if isinstance(caption, str) else "",
            }
        )
        if len(regions) >= MAX_VISION_REGIONS:
            break
    return regions


def request_region_proposals(
    session: Session,
    image_b64: str,
    *,
    project_id: str | None = None,
    page_id: str | None = None,
    confirm_paid: bool = False,
) -> VisionCompletion:
    reply = _run_routed(
        session,
        "region_proposals",
        system_prompt=VISION_PROMPT,
        user_text="Analyse the attached document page image.",
        image_b64=image_b64,
        project_id=project_id,
        page_id=page_id,
        confirm_paid=confirm_paid,
        json_mode=True,
        validator=parse_region_proposals,
    )
    return VisionCompletion(
        reply.data, reply.provider, reply.model, reply.base_url
    )


def parse_equation_latex(content: str) -> str:
    """Reduce a model reply to the LaTeX source it contains.

    Models often wrap the answer in a code fence, math delimiters or quotes even
    when the prompt forbids it. Those wrappers are removed, but the expression
    itself is never rewritten: an unreadable or empty reply is reported instead of
    guessed at.
    """
    value = _strip_code_fence(content.strip())
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1].strip()
    pairs = (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$"))
    for opening, closing in pairs:
        if (
            value.startswith(opening)
            and value.endswith(closing)
            and len(value) > len(opening) + len(closing)
        ):
            value = value[len(opening) : -len(closing)].strip()
            break
    if not value:
        raise AppError(
            502,
            "ai_equation_empty",
            "The configured AI provider returned no LaTeX for this equation.",
        )
    if len(value) > MAX_EQUATION_LENGTH:
        raise AppError(
            502,
            "ai_text_too_long",
            "The AI response was too long to use as one equation.",
        )
    return value


def request_equation_latex(
    session: Session,
    image_b64: str,
    *,
    project_id: str | None = None,
    page_id: str | None = None,
    block_id: str | None = None,
    confirm_paid: bool = False,
) -> EquationCompletion:
    reply = _run_routed(
        session,
        "equation_transcription",
        system_prompt=EQUATION_PROMPT,
        user_text="Transcribe the equation in the attached crop.",
        image_b64=image_b64,
        project_id=project_id,
        page_id=page_id,
        block_id=block_id,
        confirm_paid=confirm_paid,
        json_mode=False,
        validator=parse_equation_latex,
    )
    return EquationCompletion(
        reply.data, reply.provider, reply.model, reply.base_url
    )


def parse_table_grid(content: str) -> list[list[str]]:
    """Validate a model's table reply without filling in missing content.

    Only a complete rectangle of text cells is accepted. A ragged row, an empty
    reply, a non-text cell or a grid above the review caps is reported instead of
    being padded, truncated or guessed at, so a missing cell never silently
    becomes an empty cell in the document.
    """
    payload = _strip_code_fence(content.strip())
    try:
        body = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AppError(
            502,
            "ai_invalid_response",
            "The AI table reply was not valid JSON.",
        ) from exc
    raw = body.get("rows") if isinstance(body, dict) else body
    if not isinstance(raw, list):
        raise AppError(
            502,
            "ai_invalid_response",
            "The AI table reply had an unexpected shape.",
        )
    if not raw:
        raise AppError(
            502,
            "ai_table_empty",
            "The configured AI provider returned no table for this crop.",
        )
    if len(raw) > MAX_TABLE_ROWS:
        raise AppError(
            502,
            "ai_table_too_large",
            "The AI table reply had too many rows to review.",
        )

    rows: list[list[str]] = []
    width: int | None = None
    total_length = 0
    for raw_row in raw:
        if not isinstance(raw_row, list) or not raw_row:
            raise AppError(
                502,
                "ai_invalid_response",
                "The AI table reply had an unexpected row.",
            )
        if width is None:
            width = len(raw_row)
            if width > MAX_TABLE_COLUMNS:
                raise AppError(
                    502,
                    "ai_table_too_large",
                    "The AI table reply had too many columns to review.",
                )
        elif len(raw_row) != width:
            raise AppError(
                502,
                "ai_table_ragged",
                "The AI table reply was not a complete grid. Try again or use the "
                "local table proposal.",
            )

        row: list[str] = []
        for value in raw_row:
            if value is None:
                cell = ""
            elif isinstance(value, str):
                cell = value.strip()
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                # A number is still text the model read; a bool or a nested value
                # is not a cell and is refused instead of being stringified.
                cell = str(value)
            else:
                raise AppError(
                    502,
                    "ai_invalid_response",
                    "The AI table reply had a cell that was not text.",
                )
            if len(cell) > MAX_TABLE_CELL_LENGTH:
                raise AppError(
                    502,
                    "ai_table_too_large",
                    "An AI table cell was too long to review.",
                )
            total_length += len(cell)
            row.append(cell)
        rows.append(row)

    if width is None or width < MIN_TABLE_COLUMNS or len(rows) < MIN_TABLE_ROWS:
        raise AppError(
            502,
            "ai_table_empty",
            "The AI reply did not contain a usable table.",
        )
    if len(rows) * width > MAX_TABLE_CELLS or total_length > MAX_TEXT_LENGTH:
        raise AppError(
            502,
            "ai_table_too_large",
            "The AI table reply was too large to review.",
        )
    return rows


def request_table_grid(
    session: Session,
    image_b64: str,
    *,
    project_id: str | None = None,
    page_id: str | None = None,
    block_id: str | None = None,
    confirm_paid: bool = False,
) -> TableCompletion:
    reply = _run_routed(
        session,
        "table_structure",
        system_prompt=TABLE_PROMPT,
        user_text="Transcribe the table in the attached crop.",
        image_b64=image_b64,
        project_id=project_id,
        page_id=page_id,
        block_id=block_id,
        confirm_paid=confirm_paid,
        json_mode=True,
        validator=parse_table_grid,
    )
    return TableCompletion(reply.data, reply.provider, reply.model, reply.base_url)


def _validate_cleanup(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        raise AppError(
            502,
            "ai_empty_response",
            "The configured AI provider returned no text.",
        )
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise AppError(
            502,
            "ai_text_too_long",
            "The AI response was too long to store as a proposal.",
        )
    return cleaned


def request_cleanup(
    session: Session,
    text: str,
    *,
    project_id: str | None = None,
    page_id: str | None = None,
    block_id: str | None = None,
    confirm_paid: bool = False,
) -> Completion:
    if not text.strip():
        raise AppError(422, "ocr_block_empty", "This OCR block has no text to review.")
    if len(text) > MAX_TEXT_LENGTH:
        raise AppError(422, "ai_text_too_long", "This OCR block is too long for one AI request.")
    reply = _run_routed(
        session,
        "ocr_cleanup",
        system_prompt=SYSTEM_PROMPT,
        user_text=text,
        project_id=project_id,
        page_id=page_id,
        block_id=block_id,
        confirm_paid=confirm_paid,
        json_mode=False,
        validator=_validate_cleanup,
    )
    return Completion(reply.data, reply.provider, reply.model, reply.base_url)


def _get_page(conn, page_id: str):
    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if row is None:
        raise AppError(404, "page_not_found", "Page not found.")
    return row


def _load_block(conn, page_id: str, block_id: str):
    """Return the page, OCR block and run, refusing stale or unfinished results."""
    page = _get_page(conn, page_id)
    block = conn.execute(
        "SELECT * FROM ocr_blocks WHERE id = ? AND page_id = ?",
        (block_id, page_id),
    ).fetchone()
    if block is None:
        raise AppError(404, "ocr_block_not_found", "OCR text block not found.")
    run = conn.execute("SELECT * FROM ocr_runs WHERE id = ?", (block["run_id"],)).fetchone()
    if run is None:
        raise AppError(404, "ocr_run_not_found", "OCR run not found.")
    if run["status"] != "succeeded":
        raise AppError(409, "ocr_not_ready", "OCR has not finished for this page.")
    current_asset = page["display_asset_id"] or page["original_asset_id"]
    if run["source_asset_id"] != current_asset or int(run["rotation"]) != int(page["rotation"]):
        raise AppError(
            409,
            "ocr_stale",
            "The OCR result no longer matches the page. Run OCR again.",
        )
    return page, block, run


def _suggestion_payload(row) -> dict[str, Any]:
    page_number = row["page_number"] if "page_number" in row.keys() else None
    return {
        "id": row["id"],
        "page_id": row["page_id"],
        "page_number": page_number,
        "block_id": row["block_id"],
        "task": row["task"],
        "original_text": row["original_text"],
        "proposed_text": row["proposed_text"],
        "provider": row["provider"],
        "model": row["model"],
        "base_url": row["base_url"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _check_suggestion_status(status: AiSuggestionStatus | None) -> None:
    if status is not None and status not in {"pending", "accepted", "rejected"}:
        raise AppError(422, "invalid_ai_suggestion_status", "Unknown proposal status.")


def list_page_suggestions(
    project_dir: Path,
    page_id: str,
    status: AiSuggestionStatus | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    _check_suggestion_status(status)
    with project_db(project_dir) as conn:
        _get_page(conn, page_id)
        if status is None:
            rows = conn.execute(
                """
                SELECT s.*, p.page_number AS page_number
                FROM ai_suggestions s
                JOIN pages p ON p.id = s.page_id
                WHERE s.page_id = ?
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ?
                """,
                (page_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT s.*, p.page_number AS page_number
                FROM ai_suggestions s
                JOIN pages p ON p.id = s.page_id
                WHERE s.page_id = ? AND s.status = ?
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ?
                """,
                (page_id, status, limit),
            ).fetchall()
    return [_suggestion_payload(row) for row in rows]


def list_project_suggestions(
    project_dir: Path,
    status: AiSuggestionStatus | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List proposals across every page for the project-wide review queue."""
    _check_suggestion_status(status)
    with project_db(project_dir) as conn:
        if status is None:
            rows = conn.execute(
                """
                SELECT s.*, p.page_number AS page_number
                FROM ai_suggestions s
                JOIN pages p ON p.id = s.page_id
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT s.*, p.page_number AS page_number
                FROM ai_suggestions s
                JOIN pages p ON p.id = s.page_id
                WHERE s.status = ?
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
    return [_suggestion_payload(row) for row in rows]


def create_cleanup_suggestion(
    session: Session,
    project_dir: Path,
    page_id: str,
    block_id: str,
    *,
    project_id: str | None = None,
    confirm_paid: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with project_db(project_dir) as conn:
        _page, block, _run = _load_block(conn, page_id, block_id)
        original = block["text"] or ""
        run_id = block["run_id"]

    # The network call happens outside the database transaction.
    completion = request_cleanup(
        session,
        original,
        project_id=project_id,
        page_id=page_id,
        block_id=block_id,
        confirm_paid=confirm_paid,
    )

    now = utc_iso()
    suggestion_id = str(uuid.uuid4())
    with project_db(project_dir) as conn:
        # Re-read so a manual correction made during the request is never
        # overwritten by a proposal based on older text.
        _page, block, _run = _load_block(conn, page_id, block_id)
        if (block["text"] or "") != original:
            raise AppError(
                409,
                "ai_suggestion_stale",
                "The OCR text changed while the AI proposal was being generated.",
            )
        conn.execute(
            """
            INSERT INTO ai_suggestions (id, page_id, block_id, task, original_text,
                                        proposed_text, provider, model, base_url,
                                        status, created_at, updated_at)
            VALUES (?, ?, ?, 'ocr_cleanup', ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                suggestion_id,
                page_id,
                block_id,
                original,
                completion.text,
                completion.provider,
                completion.model,
                completion.base_url,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        suggestion = _suggestion_payload(row)

    return suggestion, ocr_service.get_run(project_dir, run_id)


def decide_suggestion(
    project_dir: Path,
    suggestion_id: str,
    status: AiSuggestionStatus,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if status not in {"accepted", "rejected"}:
        raise AppError(422, "invalid_ai_suggestion_status", "Unknown proposal decision.")
    with project_db(project_dir) as conn:
        suggestion = conn.execute(
            "SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        if suggestion is None:
            raise AppError(404, "ai_suggestion_not_found", "AI proposal not found.")
        if suggestion["status"] != "pending":
            raise AppError(
                409,
                "ai_suggestion_not_pending",
                "This AI proposal was already reviewed.",
            )
        page_id = suggestion["page_id"]
        block_id = suggestion["block_id"]
        if status == "accepted":
            _page, block, run = _load_block(conn, page_id, block_id)
            if (block["text"] or "") != suggestion["original_text"]:
                raise AppError(
                    409,
                    "ai_suggestion_stale",
                    "The OCR text changed after this AI proposal was created.",
                )
            run_id = run["id"]
        else:
            block = conn.execute(
                "SELECT * FROM ocr_blocks WHERE id = ?", (block_id,)
            ).fetchone()
            if block is None:
                raise AppError(404, "ocr_block_not_found", "OCR text block not found.")
            run_id = block["run_id"]

    if status == "accepted":
        run_payload = ocr_service.update_block(
            project_dir,
            page_id,
            block_id,
            text=suggestion["proposed_text"],
        )
    else:
        # Rejecting only discards the proposal, so it stays possible even when
        # the page changed after the proposal was created.
        run_payload = ocr_service.get_run(project_dir, run_id)

    with project_db(project_dir) as conn:
        conn.execute(
            "UPDATE ai_suggestions SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_iso(), suggestion_id),
        )
        updated = conn.execute(
            "SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        return _suggestion_payload(updated), run_payload


def decide_suggestions_bulk(
    project_dir: Path,
    suggestion_ids: list[str],
    status: AiSuggestionStatus,
) -> dict[str, Any]:
    """Decide many proposals without aborting on the first refusal.

    Each proposal goes through the same single-decision path, so accepting still
    revalidates the OCR run and text and a stale proposal is skipped rather than
    applied. The response reports one result per unique id in request order;
    failed items carry the machine-readable reason and can be retried alone.
    """
    if status not in {"accepted", "rejected"}:
        raise AppError(422, "invalid_ai_suggestion_status", "Unknown proposal decision.")

    unique_ids = list(dict.fromkeys(suggestion_ids))
    results: list[dict[str, Any]] = []
    for suggestion_id in unique_ids:
        try:
            suggestion, _run = decide_suggestion(project_dir, suggestion_id, status)
        except AppError as exc:
            results.append(
                {
                    "id": suggestion_id,
                    "status": None,
                    "error_code": exc.code,
                }
            )
            continue
        results.append(
            {
                "id": suggestion_id,
                "status": suggestion["status"],
                "error_code": None,
            }
        )

    succeeded = sum(1 for item in results if item["status"] == status)
    return {
        "results": results,
        "requested": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
    }
