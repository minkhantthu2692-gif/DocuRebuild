"""unified BYOK provider, model, key and task-routing tables

Revision ID: 0003_ai_byok
Revises: 0002_ai_usage
Create Date: 2026-11-19
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ai_byok"
down_revision: str | None = "0002_ai_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("allow_remote", sa.Boolean(), nullable=False),
        sa.Column("cost_class", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("rotation_strategy", sa.String(length=24), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("request_limit", sa.Integer(), nullable=False),
        sa.Column("monthly_budget_usd", sa.Float(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_connections_provider", "ai_connections", ["provider"]
    )

    op.create_table(
        "ai_connection_keys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("ai_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("request_limit", sa.Integer(), nullable=False),
        sa.Column("auth_failed", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_connection_keys_connection_id",
        "ai_connection_keys",
        ["connection_id"],
    )

    op.create_table(
        "ai_models",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("ai_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("family", sa.String(length=120), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("input_modalities", sa.JSON(), nullable=True),
        sa.Column("output_modalities", sa.JSON(), nullable=True),
        sa.Column("supports_tools", sa.Boolean(), nullable=True),
        sa.Column("supports_streaming", sa.Boolean(), nullable=True),
        sa.Column("pricing", sa.JSON(), nullable=True),
        sa.Column("model_metadata", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "connection_id", "model_id", name="uq_ai_model_connection"
        ),
    )
    op.create_index("ix_ai_models_connection_id", "ai_models", ["connection_id"])
    op.create_index(
        "ix_ai_models_connection_available",
        "ai_models",
        ["connection_id", "available"],
    )

    op.create_table(
        "ai_model_preferences",
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("ai_connections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("model_id", sa.String(length=200), primary_key=True),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ai_task_routes",
        sa.Column("task", sa.String(length=32), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("ai_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model_id", sa.String(length=200), nullable=True),
        sa.Column(
            "fallback_connection_id",
            sa.String(length=36),
            sa.ForeignKey("ai_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("fallback_model_id", sa.String(length=200), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("request_limit", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Existing metadata-only ledger rows remain valid; these columns describe
    # requests made through the new provider layer.
    with op.batch_alter_table("ai_usage") as batch:
        batch.add_column(sa.Column("connection_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("connection_name", sa.String(length=120), nullable=True)
        )
        batch.add_column(sa.Column("key_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("key_label", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("total_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("estimated_cost_usd", sa.Float(), nullable=True))
        batch.add_column(sa.Column("cost_source", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_usage") as batch:
        batch.drop_column("duration_ms")
        batch.drop_column("cost_source")
        batch.drop_column("estimated_cost_usd")
        batch.drop_column("total_tokens")
        batch.drop_column("output_tokens")
        batch.drop_column("input_tokens")
        batch.drop_column("key_label")
        batch.drop_column("key_id")
        batch.drop_column("connection_name")
        batch.drop_column("connection_id")

    op.drop_table("ai_task_routes")
    op.drop_table("ai_model_preferences")
    op.drop_index("ix_ai_models_connection_available", table_name="ai_models")
    op.drop_index("ix_ai_models_connection_id", table_name="ai_models")
    op.drop_table("ai_models")
    op.drop_index(
        "ix_ai_connection_keys_connection_id", table_name="ai_connection_keys"
    )
    op.drop_table("ai_connection_keys")
    op.drop_index("ix_ai_connections_provider", table_name="ai_connections")
    op.drop_table("ai_connections")
