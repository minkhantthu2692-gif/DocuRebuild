from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


PROJECT_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            format TEXT NOT NULL DEFAULT 'tiptap',
            schema_version INTEGER NOT NULL DEFAULT 1,
            content TEXT NOT NULL,
            plain_text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            mime_type TEXT,
            byte_size INTEGER NOT NULL DEFAULT 0,
            checksum TEXT,
            width INTEGER,
            height INTEGER,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pages (
            id TEXT PRIMARY KEY,
            page_number INTEGER NOT NULL,
            source_kind TEXT NOT NULL DEFAULT 'image',
            status TEXT NOT NULL DEFAULT 'imported',
            width INTEGER,
            height INTEGER,
            original_asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
            display_asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
            thumbnail_asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
            original_filename TEXT,
            rotation INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_pages_number ON pages(page_number);

        CREATE TABLE IF NOT EXISTS history_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            progress REAL NOT NULL DEFAULT 0,
            payload TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
]


def ensure_project_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    applied = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for version, sql in PROJECT_MIGRATIONS:
        if version in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, utc_iso()),
        )
        conn.commit()


@contextmanager
def project_db(project_dir: Path) -> Iterator[sqlite3.Connection]:
    """Open the per-project SQLite database, applying pending migrations."""
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(project_dir / "project.db", timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=15000")
    try:
        ensure_project_schema(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
