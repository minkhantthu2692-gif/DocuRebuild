"""Read-only project activity log.

Events are written by the services that perform the work (imports, page edits,
OCR, exports, backups) and are stored in the project's own ``project.db``. The
log is metadata only: it never contains document text, OCR output or image data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db.project_schema import project_db

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def list_events(directory: str | Path, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Return the newest project events first.

    ``created_at`` is an ISO timestamp with microseconds, and ``rowid`` breaks
    ties for events recorded inside the same instant.
    """
    with project_db(Path(directory)) as conn:
        rows = conn.execute(
            "SELECT id, event_type, summary, payload, created_at"
            " FROM history_events"
            " ORDER BY created_at DESC, rowid DESC"
            " LIMIT ?",
            (limit,),
        ).fetchall()

    events: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        events.append(
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "summary": row["summary"],
                "payload": payload if isinstance(payload, dict) else {},
                "created_at": row["created_at"],
            }
        )
    return events
