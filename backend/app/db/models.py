from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Project(Base):
    """Registry row for a locally stored project (application database)."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    directory: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base):
    """Key/value JSON settings, stored locally in SQLite."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AiUsage(Base):
    """One AI request attempt, stored as metadata only.

    No document text is recorded here. The row exists so the user can see how
    many requests were sent and so configurable rolling-window limits can be
    enforced before the next request leaves the device.
    """

    __tablename__ = "ai_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    page_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Added by the BYOK migration. Old rows keep NULL and stay readable.
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    connection_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    key_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )


class AiConnection(Base):
    """One user-created provider connection; secrets live in the encrypted store."""

    __tablename__ = "ai_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    allow_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cost_class: Mapped[str] = mapped_column(String(16), nullable=False, default="local")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rotation_strategy: Mapped[str] = mapped_column(
        String(24), nullable=False, default="priority"
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AiConnectionKey(Base):
    """Metadata for one API key; the key itself is never stored in SQLite."""

    __tablename__ = "ai_connection_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auth_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AiModel(Base):
    """One model discovered from a connection, with only verified metadata."""

    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint("connection_id", "model_id", name="uq_ai_model_connection"),
        Index("ix_ai_models_connection_available", "connection_id", "available"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    family: Mapped[str | None] = mapped_column(String(120), nullable=True)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_modalities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    output_modalities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    supports_tools: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    supports_streaming: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pricing: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="discovered")
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AiModelPreference(Base):
    """User preference and last-use time for one provider model id."""

    __tablename__ = "ai_model_preferences"

    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_connections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AiTaskRoute(Base):
    """Assign one application task to a connection and discovered model."""

    __tablename__ = "ai_task_routes"

    task: Mapped[str] = mapped_column(String(32), primary_key=True)
    connection_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fallback_connection_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    fallback_model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
