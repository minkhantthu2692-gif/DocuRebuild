from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AiUsage
from app.schemas.ai import AiUsageOutcome

WINDOW_HOURS = 24
RECENT_LIMIT = 20


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
        "recent": [_entry(row) for row in rows[:RECENT_LIMIT]],
    }
