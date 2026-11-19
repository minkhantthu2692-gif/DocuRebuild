from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AiUsage, Project

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


def _month_start() -> datetime:
    now = _utc_naive_now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


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
        "connection_id": row.connection_id,
        "connection_name": row.connection_name,
        "key_id": row.key_id,
        "key_label": row.key_label,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "total_tokens": row.total_tokens,
        "estimated_cost_usd": row.estimated_cost_usd,
        "cost_source": row.cost_source,
        "duration_ms": row.duration_ms,
        "created_at": row.created_at.isoformat(),
    }


def _window_rows(session: Session) -> list[AiUsage]:
    statement = (
        select(AiUsage)
        .where(AiUsage.created_at >= _window_start())
        .order_by(AiUsage.created_at.desc())
    )
    return list(session.execute(statement).scalars().all())


def count_attempts(session: Session, **filters: Any) -> int:
    """Count attempts in the rolling window for an optional metadata filter."""
    statement = select(func.count()).select_from(AiUsage).where(
        AiUsage.created_at >= _window_start()
    )
    for field, value in filters.items():
        column = getattr(AiUsage, field, None)
        if column is not None and value is not None:
            statement = statement.where(column == value)
    return int(session.execute(statement).scalar_one())


def monthly_cost(session: Session, connection_id: str | None = None) -> float:
    statement = select(func.coalesce(func.sum(AiUsage.estimated_cost_usd), 0.0)).where(
        AiUsage.created_at >= _month_start(),
        AiUsage.estimated_cost_usd.is_not(None),
    )
    if connection_id is not None:
        statement = statement.where(AiUsage.connection_id == connection_id)
    return float(session.execute(statement).scalar_one())


def ensure_within_limit(session: Session, request_limit: int) -> None:
    """Refuse a new request when the global rolling-window cap is reached."""
    if request_limit <= 0:
        return
    if count_attempts(session) >= request_limit:
        raise AppError(
            429,
            "ai_request_limit_reached",
            "The global AI request limit for the last 24 hours has been reached.",
        )


def record_attempt(
    session: Session,
    *,
    provider: str,
    model: str,
    task: str,
    outcome: str,
    error_code: str | None,
    project_id: str | None,
    page_id: str | None,
    block_id: str | None,
    connection_id: str | None = None,
    connection_name: str | None = None,
    key_id: str | None = None,
    key_label: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    cost_source: str | None = None,
    duration_ms: int | None = None,
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
            connection_id=connection_id,
            connection_name=connection_name,
            key_id=key_id,
            key_label=key_label,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            cost_source=cost_source,
            duration_ms=duration_ms,
            created_at=_utc_naive_now(),
        )
    )


def _task_counts(rows: list[AiUsage]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.task] = counts.get(row.task, 0) + 1
    known = [task for task in TASK_ORDER if task in counts]
    unknown = sorted(task for task in counts if task not in TASK_ORDER)
    return [{"task": task, "used": counts[task]} for task in (*known, *unknown)]


def _connection_counts(rows: list[AiUsage]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not row.connection_id:
            continue
        bucket = buckets.setdefault(
            row.connection_id,
            {
                "connection_id": row.connection_id,
                "connection_name": row.connection_name or row.connection_id,
                "provider": row.provider,
                "used": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
                "unpriced_requests": 0,
            },
        )
        bucket["used"] += 1
        if row.input_tokens is not None:
            bucket["input_tokens"] += row.input_tokens
        if row.output_tokens is not None:
            bucket["output_tokens"] += row.output_tokens
        if row.estimated_cost_usd is not None:
            bucket["estimated_cost_usd"] += row.estimated_cost_usd
        else:
            bucket["unpriced_requests"] += 1
    return sorted(buckets.values(), key=lambda item: item["used"], reverse=True)


def usage_summary(session: Session, request_limit: int = 0) -> dict[str, Any]:
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
        "input_tokens": sum(row.input_tokens or 0 for row in rows),
        "output_tokens": sum(row.output_tokens or 0 for row in rows),
        "total_tokens": sum(row.total_tokens or 0 for row in rows),
        "estimated_cost_usd": sum(row.estimated_cost_usd or 0.0 for row in rows),
        "unpriced_requests": sum(
            1 for row in rows if row.estimated_cost_usd is None
        ),
        "monthly_cost_usd": monthly_cost(session),
        "by_task": _task_counts(rows),
        "by_connection": _connection_counts(rows),
        "recent": [_entry(row) for row in rows[:RECENT_LIMIT]],
    }


def usage_history(
    session: Session,
    *,
    limit: int,
    offset: int,
    outcome: str | None = None,
    task: str | None = None,
    connection_id: str | None = None,
    project_id: str | None = None,
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
    if connection_id is not None:
        filters.append(AiUsage.connection_id == connection_id)
    if project_id is not None:
        filters.append(AiUsage.project_id == project_id)

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
