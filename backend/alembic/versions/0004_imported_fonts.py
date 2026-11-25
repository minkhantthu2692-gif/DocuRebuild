"""local imported font library

Revision ID: 0004_imported_fonts
Revises: 0003_ai_byok
Create Date: 2026-11-25
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_imported_fonts"
down_revision: str | None = "0003_ai_byok"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "imported_fonts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("family", sa.String(length=160), nullable=False),
        sa.Column("style", sa.String(length=80), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("italic", sa.Boolean(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stored_name", name="uq_imported_fonts_stored_name"),
        sa.UniqueConstraint("sha256", name="uq_imported_fonts_sha256"),
    )
    op.create_index("ix_imported_fonts_family", "imported_fonts", ["family"])


def downgrade() -> None:
    op.drop_index("ix_imported_fonts_family", table_name="imported_fonts")
    op.drop_table("imported_fonts")
