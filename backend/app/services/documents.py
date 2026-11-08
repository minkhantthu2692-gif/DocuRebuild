from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.project_schema import project_db, utc_iso

DEFAULT_CONTENT: dict[str, Any] = {
    "type": "doc",
    "content": [{"type": "paragraph"}],
}


def _now() -> str:
    return utc_iso()


def ensure_document_row(conn) -> None:
    row = conn.execute("SELECT id FROM documents WHERE id = 'main'").fetchone()
    if row is None:
        now = _now()
        conn.execute(
            """
            INSERT INTO documents (id, title, format, schema_version, content, plain_text,
                                   created_at, updated_at)
            VALUES ('main', '', 'tiptap', 1, ?, '', ?, ?)
            """,
            ('{"type":"doc","content":[{"type":"paragraph"}]}', now, now),
        )


def read_document(project_dir: Path) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        ensure_document_row(conn)
        row = conn.execute("SELECT * FROM documents WHERE id = 'main'").fetchone()
    import json

    return {
        "format": row["format"],
        "schema_version": row["schema_version"],
        "content": json.loads(row["content"]),
        "plain_text": row["plain_text"],
        "updated_at": row["updated_at"],
    }


def write_document(
    project_dir: Path, content: dict[str, Any], plain_text: str
) -> dict[str, Any]:
    import json

    with project_db(project_dir) as conn:
        ensure_document_row(conn)
        now = _now()
        conn.execute(
            "UPDATE documents SET content = ?, plain_text = ?, updated_at = ? WHERE id = 'main'",
            (json.dumps(content, ensure_ascii=False), plain_text, now),
        )
        row = conn.execute("SELECT * FROM documents WHERE id = 'main'").fetchone()
    return {
        "format": row["format"],
        "schema_version": row["schema_version"],
        "content": json.loads(row["content"]),
        "plain_text": row["plain_text"],
        "updated_at": row["updated_at"],
    }


def document_updated_at(project_dir: Path) -> datetime | None:
    try:
        with project_db(project_dir) as conn:
            ensure_document_row(conn)
            row = conn.execute(
                "SELECT updated_at FROM documents WHERE id = 'main'"
            ).fetchone()
    except Exception:
        return None
    if not row or not row["updated_at"]:
        return None
    try:
        return datetime.fromisoformat(row["updated_at"])
    except ValueError:
        return None
