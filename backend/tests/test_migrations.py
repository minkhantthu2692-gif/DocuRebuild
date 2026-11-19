from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def test_byok_migration_preserves_legacy_usage_rows(tmp_path, monkeypatch) -> None:
    """An existing database upgrades in place, and the step is reversible."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DOCUREBUILD_DATA_DIR", str(data_dir))

    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        database = data_dir / "app.db"
        config = _config()
        command.upgrade(config, "0002_ai_usage")

        with sqlite3.connect(database) as connection:
            connection.execute(
                "INSERT INTO ai_usage ("
                "id, provider, model, task, outcome, error_code, project_id, page_id,"
                " block_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "legacy-row",
                    "ollama",
                    "qwen2.5:7b",
                    "text",
                    "success",
                    None,
                    "project-1",
                    "page-1",
                    "block-1",
                    "2026-01-01 00:00:00.000000",
                ),
            )
            connection.commit()

        command.upgrade(config, "head")

        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT provider, model, task, outcome, connection_id,"
                " input_tokens, total_tokens, cost_source"
                " FROM ai_usage WHERE id = 'legacy-row'"
            ).fetchone()
            tables = {
                name
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            revision = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()

        assert row == ("ollama", "qwen2.5:7b", "text", "success", None, None, None, None)
        assert revision == ("0003_ai_byok",)
        assert {
            "ai_connections",
            "ai_connection_keys",
            "ai_models",
            "ai_model_preferences",
            "ai_task_routes",
        } <= tables

        command.downgrade(config, "0002_ai_usage")

        with sqlite3.connect(database) as connection:
            legacy = connection.execute(
                "SELECT provider, model, outcome FROM ai_usage WHERE id = 'legacy-row'"
            ).fetchone()
            tables = {
                name
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

        assert legacy == ("ollama", "qwen2.5:7b", "success")
        assert not {
            "ai_connections",
            "ai_connection_keys",
            "ai_models",
            "ai_model_preferences",
            "ai_task_routes",
        } & tables
    finally:
        get_settings.cache_clear()
