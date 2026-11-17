"""Per-project page header and footer text for paginated exports.

The layout belongs to the project, not to the application, because it describes
the reconstructed document (for example a running head or a source citation)
rather than a global preference. It is stored in the project database, so it
travels with the project's own backups and is never written to app settings.

The text is plain, single-line text. ``{page}``, ``{pages}`` and ``{title}`` are
optional tokens: Word writes real page fields for the first two, and PDF resolves
them per page. Nothing here contacts a network service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.project_schema import project_db, utc_iso

LAYOUT_ID = "main"
MAX_LAYOUT_TEXT = 200


def _payload(row) -> dict[str, Any]:
    return {
        "header_text": row["header_text"],
        "footer_text": row["footer_text"],
        "show_page_numbers": bool(row["show_page_numbers"]),
        "updated_at": row["updated_at"],
    }


def _ensure_row(conn) -> None:
    row = conn.execute(
        "SELECT id FROM document_layout WHERE id = ?", (LAYOUT_ID,)
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO document_layout
                (id, header_text, footer_text, show_page_numbers, updated_at)
            VALUES (?, '', '', 1, ?)
            """,
            (LAYOUT_ID, utc_iso()),
        )


def read_layout(project_dir: Path) -> dict[str, Any]:
    """Return the stored header/footer, creating the empty default on first read."""
    with project_db(project_dir) as conn:
        _ensure_row(conn)
        row = conn.execute(
            "SELECT * FROM document_layout WHERE id = ?", (LAYOUT_ID,)
        ).fetchone()
        return _payload(row)


def write_layout(
    project_dir: Path,
    *,
    header_text: str,
    footer_text: str,
    show_page_numbers: bool,
) -> dict[str, Any]:
    """Replace the project's page header/footer and return the stored values."""
    with project_db(project_dir) as conn:
        now = utc_iso()
        conn.execute(
            """
            INSERT INTO document_layout
                (id, header_text, footer_text, show_page_numbers, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                header_text = excluded.header_text,
                footer_text = excluded.footer_text,
                show_page_numbers = excluded.show_page_numbers,
                updated_at = excluded.updated_at
            """,
            (
                LAYOUT_ID,
                header_text,
                footer_text,
                1 if show_page_numbers else 0,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM document_layout WHERE id = ?", (LAYOUT_ID,)
        ).fetchone()
        return _payload(row)
