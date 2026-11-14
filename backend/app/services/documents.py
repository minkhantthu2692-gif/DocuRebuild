from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.errors import AppError
from app.db.project_schema import project_db, utc_iso

DEFAULT_CONTENT: dict[str, Any] = {
    "type": "doc",
    "content": [{"type": "paragraph"}],
}

# Automatic snapshots are created at most once per interval for continuous
# editing, so a long typing session does not fill the history with near-identical
# versions. Restoring a version always snapshots the state it replaces.
REVISION_INTERVAL_SECONDS = 300
# Oldest revisions beyond this count are pruned. The live document is never a
# revision, so pruning can never remove the current content.
REVISION_LIMIT = 100
REVISION_SOURCES = ("autosave", "manual")
PREVIEW_LENGTH = 200


def _now() -> str:
    return utc_iso()


def _encode(content: dict[str, Any]) -> str:
    return json.dumps(content, ensure_ascii=False)


def _canonical(value: str | dict[str, Any]) -> str:
    """Stable representation used only for equality checks, never for storage."""
    parsed = json.loads(value) if isinstance(value, str) else value
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _preview(plain_text: str) -> str:
    return " ".join(plain_text.split())[:PREVIEW_LENGTH]


_DEFAULT_CONTENT_CANONICAL = _canonical(DEFAULT_CONTENT)


def _is_default_document(raw: str) -> bool:
    """True for the untouched initial document, which is not worth a version."""
    return _canonical(raw) == _DEFAULT_CONTENT_CANONICAL


def _document_payload(row) -> dict[str, Any]:
    return {
        "format": row["format"],
        "schema_version": row["schema_version"],
        "content": json.loads(row["content"]),
        "plain_text": row["plain_text"],
        "updated_at": row["updated_at"],
    }


def _revision_summary(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source": row["source"],
        "preview": _preview(row["plain_text"]),
        "character_count": len(row["plain_text"]),
        "created_at": row["created_at"],
    }


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


def _insert_revision(
    conn, content: str, plain_text: str, source: str, created_at: str
) -> str:
    revision_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO document_revisions (id, content, plain_text, source, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (revision_id, content, plain_text, source, created_at),
    )
    conn.execute(
        """
        DELETE FROM document_revisions
        WHERE id NOT IN (
            SELECT id FROM document_revisions
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
        )
        """,
        (REVISION_LIMIT,),
    )
    return revision_id


def _snapshot_previous(conn, previous_row, now: str, *, force: bool) -> None:
    """Store the state that is about to be overwritten.

    The newest revision is never duplicated, and automatic snapshots respect the
    coalescing interval. A forced snapshot (restore, manual checkpoint) ignores
    the interval but still skips an identical newest revision.
    """
    newest = conn.execute(
        """
        SELECT content, created_at FROM document_revisions
        ORDER BY created_at DESC, rowid DESC LIMIT 1
        """
    ).fetchone()
    if not force and _is_default_document(previous_row["content"]):
        return
    if newest is not None and _canonical(newest["content"]) == _canonical(
        previous_row["content"]
    ):
        return

    if not force and newest is not None:
        try:
            last = datetime.fromisoformat(newest["created_at"])
        except ValueError:
            last = None
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < REVISION_INTERVAL_SECONDS:
                return

    _insert_revision(
        conn,
        previous_row["content"],
        previous_row["plain_text"],
        "autosave",
        now,
    )


def _update_document(
    conn,
    content: dict[str, Any],
    plain_text: str,
    *,
    force_snapshot: bool = False,
) -> dict[str, Any]:
    ensure_document_row(conn)
    now = _now()
    previous = conn.execute(
        "SELECT content, plain_text FROM documents WHERE id = 'main'"
    ).fetchone()
    encoded = _encode(content)
    if previous is not None and _canonical(previous["content"]) != _canonical(content):
        _snapshot_previous(conn, previous, now, force=force_snapshot)
    conn.execute(
        "UPDATE documents SET content = ?, plain_text = ?, updated_at = ? WHERE id = 'main'",
        (encoded, plain_text, now),
    )
    row = conn.execute("SELECT * FROM documents WHERE id = 'main'").fetchone()
    return _document_payload(row)


def read_document(project_dir: Path) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        ensure_document_row(conn)
        row = conn.execute("SELECT * FROM documents WHERE id = 'main'").fetchone()
        return _document_payload(row)


def write_document(
    project_dir: Path, content: dict[str, Any], plain_text: str
) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        return _update_document(conn, content, plain_text)


def replace_document(
    project_dir: Path, content: dict[str, Any], plain_text: str
) -> dict[str, Any]:
    """Replace the live document and always snapshot the state it replaces.

    Used by a restore from a backup, where the previous text must stay available
    in the local version history even when it was edited moments ago.
    """
    with project_db(project_dir) as conn:
        return _update_document(conn, content, plain_text, force_snapshot=True)


def list_revisions(project_dir: Path, limit: int = 50) -> list[dict[str, Any]]:
    with project_db(project_dir) as conn:
        ensure_document_row(conn)
        rows = conn.execute(
            """
            SELECT id, plain_text, source, created_at FROM document_revisions
            ORDER BY created_at DESC, rowid DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_revision_summary(row) for row in rows]


def create_revision(project_dir: Path, source: str = "manual") -> dict[str, Any]:
    """Checkpoint the current saved document as a new revision."""
    if source not in REVISION_SOURCES:
        raise ValueError(f"Unsupported revision source: {source}")
    with project_db(project_dir) as conn:
        ensure_document_row(conn)
        document = conn.execute(
            "SELECT content, plain_text FROM documents WHERE id = 'main'"
        ).fetchone()
        newest = conn.execute(
            """
            SELECT id, content, plain_text, source, created_at FROM document_revisions
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """
        ).fetchone()
        if newest is not None and _canonical(newest["content"]) == _canonical(
            document["content"]
        ):
            return _revision_summary(newest)
        revision_id = _insert_revision(
            conn, document["content"], document["plain_text"], source, _now()
        )
        row = conn.execute(
            "SELECT id, plain_text, source, created_at FROM document_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        return _revision_summary(row)


def read_revision(project_dir: Path, revision_id: str) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        row = conn.execute(
            "SELECT * FROM document_revisions WHERE id = ?", (revision_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                404, "revision_not_found", "The document revision was not found."
            )
        return {
            **_revision_summary(row),
            "content": json.loads(row["content"]),
            "plain_text": row["plain_text"],
        }


def restore_revision(project_dir: Path, revision_id: str) -> dict[str, Any]:
    """Make a stored revision the live document.

    The state being replaced is always snapshotted first, so a restore can itself
    be undone from the same history.
    """
    with project_db(project_dir) as conn:
        row = conn.execute(
            "SELECT * FROM document_revisions WHERE id = ?", (revision_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                404, "revision_not_found", "The document revision was not found."
            )
        return _update_document(
            conn,
            json.loads(row["content"]),
            row["plain_text"],
            force_snapshot=True,
        )


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
