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
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS ocr_runs (
            id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'queued',
            engine TEXT NOT NULL DEFAULT 'tesseract',
            engine_version TEXT,
            languages TEXT NOT NULL DEFAULT 'eng',
            source_asset_id TEXT,
            rotation INTEGER NOT NULL DEFAULT 0,
            mean_confidence REAL,
            text TEXT NOT NULL DEFAULT '',
            error TEXT,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ocr_runs_page_created
            ON ocr_runs(page_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS ocr_blocks (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES ocr_runs(id) ON DELETE CASCADE,
            page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            block_index INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'paragraph',
            text TEXT NOT NULL DEFAULT '',
            confidence REAL,
            x INTEGER,
            y INTEGER,
            width INTEGER,
            height INTEGER,
            line_count INTEGER NOT NULL DEFAULT 0,
            word_count INTEGER NOT NULL DEFAULT 0,
            verified INTEGER NOT NULL DEFAULT 0,
            corrected INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ocr_blocks_run
            ON ocr_blocks(run_id, block_index);
        CREATE INDEX IF NOT EXISTS idx_ocr_blocks_page
            ON ocr_blocks(page_id);
        """,
    ),
    (
        3,
        """
        ALTER TABLE pages ADD COLUMN pdf_page_number INTEGER;
        """,
    ),
    (
        4,
        """
        ALTER TABLE pages ADD COLUMN edits TEXT NOT NULL DEFAULT '{}';
        """,
    ),
    (
        5,
        """
        ALTER TABLE jobs ADD COLUMN completed_at TEXT;
        ALTER TABLE jobs ADD COLUMN total_pages INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE jobs ADD COLUMN imported_pages INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE jobs ADD COLUMN current_file TEXT;
        ALTER TABLE jobs ADD COLUMN error_code TEXT;
        CREATE INDEX IF NOT EXISTS idx_jobs_kind_status
            ON jobs(kind, status, created_at DESC);
        """,
    ),
    (
        6,
        """
        CREATE TABLE IF NOT EXISTS elements (
            id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'figure',
            asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
            source_asset_id TEXT,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            caption TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'manual',
            verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_elements_page
            ON elements(page_id, created_at DESC);
        """,
    ),
    (
        7,
        """
        ALTER TABLE elements ADD COLUMN text TEXT NOT NULL DEFAULT '';
        ALTER TABLE elements ADD COLUMN text_confidence REAL;
        ALTER TABLE elements ADD COLUMN text_engine TEXT;
        ALTER TABLE elements ADD COLUMN text_engine_version TEXT;
        ALTER TABLE elements ADD COLUMN text_languages TEXT NOT NULL DEFAULT '';
        ALTER TABLE elements ADD COLUMN text_corrected INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE elements ADD COLUMN text_updated_at TEXT;
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
