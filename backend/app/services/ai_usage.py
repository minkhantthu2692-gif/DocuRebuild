from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AiUsage, Project
from app.schemas.ai import AiUsageOutcome

WINDOW_HOURS = 24
RECENT_LIMIT = 20
HISTORY_LIMIT = 25
HISTORY_MAX_LIMIT = 100

# Stable display order for the known tasks. Any other stored task name (older
# rows or a future task) is listed afterwards, alphabetically, instead of being
# dropped or folded into a catch-all bucket.
TASK_ORDER = (
    "ocr_cleanup",
    "region_proposals",
    "equation_transcription",
    "table_structure",
)


def _utc_naive_now() -> datetime:
    """Match SQLAlchemy's SQLite storage, which drops the timezone offset."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _window_start() -> datetime:
    return _utc_naive_now() - timedelta(hours=WINDOW_HOURS)


def _entry(row: AiUsage) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider": row.provider,
        "model": row.model,
        "task": row.task,
        "outcome": row.outcome,
        "error_code": row.error_code,
        "project_id": row.project_id,
        "page_id": row.page_id,
        "block_id": row.block_id,
        "created_at": row.created_at.isoformat(),
    }


def _window_rows(session: Session) -> list[AiUsage]:
    statement = (
        select(AiUsage)
        .where(AiUsage.created_at >= _window_start())
        .order_by(AiUsage.created_at.desc())
    )
    return list(session.execute(statement).scalars().all())


def ensure_within_limit(session: Session, request_limit: int) -> None:
    """Refuse a new request when the user's rolling-window cap is reached."""
    if request_limit <= 0:
        return
    used = len(_window_rows(session))
    if used >= request_limit:
        raise AppError(
            429,
            "ai_request_limit_reached",
            "The local AI request limit for the last 24 hours has been reached.",
        )


def record_attempt(
    session: Session,
    *,
    provider: str,
    model: str,
    task: str,
    outcome: AiUsageOutcome,
    error_code: str | None,
    project_id: str | None,
    page_id: str | None,
    block_id: str | None,
) -> None:
    session.add(
        AiUsage(
            id=str(uuid.uuid4()),
            provider=provider,
            model=model,
            task=task,
            outcome=outcome,
            error_code=error_code,
            project_id=project_id,
            page_id=page_id,
            block_id=block_id,
            created_at=_utc_naive_now(),
        )
    )


def _task_counts(rows: list[AiUsage]) -> list[dict[str, Any]]:
    """Count attempts per task in the window, errors included.

    Errors consume the rolling budget just as successes do, so the breakdown
    counts every attempt and never estimates cost or token usage.
    """
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.task] = counts.get(row.task, 0) + 1
    known = [task for task in TASK_ORDER if task in counts]
    unknown = sorted(task for task in counts if task not in TASK_ORDER)
    return [{"task": task, "used": counts[task]} for task in (*known, *unknown)]


def usage_summary(session: Session, request_limit: int) -> dict[str, Any]:
    rows = _window_rows(session)
    used = len(rows)
    successful = sum(1 for row in rows if row.outcome == "success")
    failed = used - successful
    remaining = None if request_limit <= 0 else max(request_limit - used, 0)
    return {
        "window_hours": WINDOW_HOURS,
        "request_limit": request_limit,
        "used": used,
        "remaining": remaining,
        "successful": successful,
        "failed": failed,
        "by_task": _task_counts(rows),
        "recent": [_entry(row) for row in rows[:RECENT_LIMIT]],
    }


def usage_history(
    session: Session,
    *,
    limit: int,
    offset: int,
    outcome: AiUsageOutcome | None = None,
    task: str | None = None,
) -> dict[str, Any]:
    """Page through the local AI ledger, newest first, with project names.

    The ledger intentionally stores metadata only, so this never joins document
    text or model replies. A deleted project leaves its history intact and shows
    no project name.
    """
    filters = []
    if outcome is not None:
        filters.append(AiUsage.outcome == outcome)
    if task is not None:
        filters.append(AiUsage.task == task)

    total = int(
        session.execute(
            select(func.count()).select_from(AiUsage).where(*filters)
        ).scalar_one()
    )
    statement = (
        select(AiUsage, Project.name)
        .outerjoin(Project, AiUsage.project_id == Project.id)
        .where(*filters)
        .order_by(AiUsage.created_at.desc(), AiUsage.id.desc())
        .limit(limit)
        .offset(offset)
    )
    entries: list[dict[str, Any]] = []
    for usage, project_name in session.execute(statement).all():
        entry = _entry(usage)
        entry["project_name"] = project_name
        entries.append(entry)
    return {
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
