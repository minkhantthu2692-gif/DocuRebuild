from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.conftest import upload_pages


class _StubState:
    def __init__(self) -> None:
        self.models = [
            {
                "id": "text-large",
                "name": "Text Large",
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                "context_length": 128000,
            },
            {
                "id": "vision-large",
                "name": "Vision Large",
                "architecture": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                },
                "context_length": 64000,
            },
        ]
        self.chat_reply = "Cleaned text"
        self.vision_reply = json.dumps(
            {
                "regions": [
                    {
                        "kind": "figure",
                        "x": 0.1,
                        "y": 0.2,
                        "width": 0.3,
                        "height": 0.4,
                        "caption": "Figure 1",
                    }
                ]
            }
        )
        self.auth_headers: list[str | None] = []
        self.paths: list[str] = []
        self.last_payload: dict | None = None
        # keyed by the Bearer token: ("once" | "always", status)
        self.failures: dict[str, tuple[str, int]] = {}
        self.retry_after = "30"

    def failure_for(self, header: str | None) -> int | None:
        token = (header or "").removeprefix("Bearer ").strip()
        entry = self.failures.get(token)
        if entry is None:
            return None
        mode, status = entry
        if mode == "once":
            del self.failures[token]
        return status


def _respond(handler, status: int, payload: dict, retry_after: str | None = None) -> None:
    raw = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    if retry_after:
        handler.send_header("Retry-After", retry_after)
    handler.end_headers()
    handler.wfile.write(raw)


@pytest.fixture()
def stub_ai():
    state = _StubState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            state.paths.append(self.path)
            state.auth_headers.append(self.headers.get("Authorization"))
            status = state.failure_for(self.headers.get("Authorization"))
            if status is not None:
                _respond(self, status, {"error": "stub"}, state.retry_after)
                return
            if self.path == "/v1/models":
                _respond(self, 200, {"data": state.models})
            elif self.path == "/api/tags":
                _respond(
                    self,
                    200,
                    {
                        "models": [
                            {
                                "name": "qwen2.5:7b",
                                "model": "qwen2.5:7b",
                                "details": {"family": "qwen2"},
                            },
                            {"name": "llava:7b", "model": "llava:7b"},
                        ]
                    },
                )
            elif self.path == "/api/version":
                _respond(self, 200, {"version": "0.5.1"})
            else:
                _respond(self, 404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            state.paths.append(self.path)
            state.auth_headers.append(self.headers.get("Authorization"))
            status = state.failure_for(self.headers.get("Authorization"))
            if status is not None:
                _respond(self, status, {"error": "stub"}, state.retry_after)
                return
            try:
                payload = json.loads(body or b"{}")
            except json.JSONDecodeError:
                _respond(self, 400, {"error": "bad json"})
                return
            state.last_payload = payload
            message = payload.get("messages", [{}])[-1]
            is_vision = bool(message.get("images")) or isinstance(
                message.get("content"), list
            )
            content = state.vision_reply if is_vision else state.chat_reply
            if self.path == "/v1/chat/completions":
                _respond(
                    self,
                    200,
                    {
                        "choices": [{"message": {"role": "assistant", "content": content}}],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 20,
                            "total_tokens": 30,
                        },
                    },
                )
            elif self.path == "/api/chat":
                _respond(
                    self,
                    200,
                    {
                        "message": {"role": "assistant", "content": content},
                        "prompt_eval_count": 10,
                        "eval_count": 20,
                    },
                )
            else:
                _respond(self, 404, {"error": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    yield SimpleNamespace(base_url=base, base_url_v1=f"{base}/v1", state=state)
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _create_connection(
    client: TestClient,
    *,
    base_url: str,
    provider: str = "openai_compatible",
    name: str = "Test provider",
    keys: list[tuple[str, str, int]] | None = None,
    cost_class: str = "local",
) -> dict:
    response = client.post(
        "/api/ai/connections",
        json={
            "provider": provider,
            "name": name,
            "base_url": base_url,
            "allow_remote": False,
            "cost_class": cost_class,
        },
    )
    assert response.status_code == 201, response.text
    connection = response.json()
    for label, key, priority in keys or [("Primary", "key-a", 10)]:
        added = client.post(
            f"/api/ai/connections/{connection['id']}/keys",
            json={"label": label, "api_key": key, "priority": priority},
        )
        assert added.status_code == 201, added.text
    refreshed = client.get(f"/api/ai/connections/{connection['id']}")
    assert refreshed.status_code == 200, refreshed.text
    return refreshed.json()


def _configure(
    client: TestClient,
    connection: dict,
    *,
    task: str,
    model_id: str,
    fallback: tuple[dict, str] | None = None,
    **route: object,
) -> dict:
    payload: dict = {
        "connection_id": connection["id"],
        "model_id": model_id,
        **route,
    }
    if fallback is not None:
        payload["fallback_connection_id"] = fallback[0]["id"]
        payload["fallback_model_id"] = fallback[1]
    response = client.put(f"/api/ai/routes/{task}", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _test(client: TestClient, connection: dict, api_key: str | None = None) -> dict:
    response = client.post(
        f"/api/ai/connections/{connection['id']}/test",
        json={"api_key": api_key} if api_key else None,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _engine_available() -> dict:
    return {
        "engine": "tesseract",
        "available": True,
        "version": "5.3.3",
        "command": "tesseract",
        "tessdata_dir": None,
        "languages": ["eng", "mya"],
        "preferred_languages": ["eng", "mya"],
        "reason": None,
        "setup_hint": None,
    }


def _fake_ocr_result() -> dict:
    return {
        "engine_version": "5.3.3",
        "text": "Chapter One\n\nA local OCR result.",
        "mean_confidence": 91.5,
        "blocks": [
            {
                "block_index": 1,
                "kind": "heading",
                "text": "Chapter One",
                "confidence": 96.0,
                "x": 20,
                "y": 30,
                "width": 240,
                "height": 40,
                "line_count": 1,
                "word_count": 2,
            },
            {
                "block_index": 2,
                "kind": "paragraph",
                "text": "A local OCR result.",
                "confidence": 87.0,
                "x": 20,
                "y": 100,
                "width": 360,
                "height": 60,
                "line_count": 2,
                "word_count": 4,
            },
        ],
    }


def _wait_for_run(client: TestClient, project_id: str, page_id: str) -> dict:
    deadline = time.monotonic() + 5.0
    latest = None
    while time.monotonic() < deadline:
        latest = client.get(f"/api/projects/{project_id}/pages/{page_id}/ocr").json()
        if latest and latest["status"] in {"succeeded", "failed"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"OCR run did not finish: {latest}")


def _ocr_page(client: TestClient, project: dict, monkeypatch, name: str) -> tuple[dict, dict]:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_perform_ocr", lambda *args, **kwargs: _fake_ocr_result())
    page = upload_pages(client, project["id"], [name])[0]
    response = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 202, response.text
    return page, _wait_for_run(client, project["id"], page["id"])


def test_provider_catalog_has_no_model_catalog(client: TestClient) -> None:
    response = client.get("/api/ai/providers")
    assert response.status_code == 200
    providers = {item["id"]: item for item in response.json()["providers"]}
    for provider in (
        "openai",
        "anthropic",
        "gemini",
        "openrouter",
        "groq",
        "mistral",
        "deepseek",
        "xai",
        "together",
        "fireworks",
        "cerebras",
        "perplexity",
        "openai_compatible",
        "ollama",
    ):
        assert provider in providers
    assert not any("models" in item for item in providers.values())


def test_connection_key_discovery_and_route(client: TestClient, stub_ai) -> None:
    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    assert connection["status"] == "untested"
    assert connection["key_count"] == 1
    # The write-only key must never come back.
    assert "key-a" not in json.dumps(connection)

    result = _test(client, connection)
    assert result["status"] == "connected"
    assert result["models_found"] == 2

    models = client.get(
        f"/api/ai/connections/{connection['id']}/models"
    ).json()
    by_id = {item["model_id"]: item for item in models}
    assert by_id["vision-large"]["input_modalities"] == ["image", "text"]
    assert by_id["text-large"]["context_window"] == 128000
    assert by_id["text-large"]["pricing"]["prompt"] == 0.000001
    assert by_id["text-large"]["available"] is True

    route = _configure(client, connection, task="ocr_cleanup", model_id="text-large")
    assert route["configured"] is True
    assert route["capability"] == "text"


def test_connection_key_is_encrypted_and_never_in_sqlite(
    client: TestClient, stub_ai
) -> None:
    from app.core.config import get_settings
    from app.db.session import get_session_factory
    from app.db.models import AiConnectionKey

    _create_connection(client, base_url=stub_ai.base_url_v1)
    data_dir = get_settings().data_dir
    secret_file = data_dir / "secrets" / "ai_keys.enc"
    assert secret_file.exists()
    assert b"key-a" not in secret_file.read_bytes()
    assert (data_dir / "secrets" / "ai_keys.key").exists()

    with get_session_factory()() as session:
        row = session.query(AiConnectionKey).one()
        stored = {column.name: str(getattr(row, column.name)) for column in row.__table__.columns}
        assert "key-a" not in json.dumps(stored)


def test_invalid_key_marks_key_and_connection(client: TestClient, stub_ai) -> None:
    connection = _create_connection(
        client, base_url=stub_ai.base_url_v1, keys=[("Primary", "bad-key", 10)]
    )
    stub_ai.state.failures["bad-key"] = ("always", 401)
    result = _test(client, connection)
    assert result["status"] == "auth_failed"
    keys = client.get(f"/api/ai/connections/{connection['id']}/keys").json()
    assert keys[0]["auth_failed"] is True
    assert keys[0]["status"] == "auth_failed"


def test_key_failover_rotates_to_second_key(client: TestClient, stub_ai) -> None:
    connection = _create_connection(
        client,
        base_url=stub_ai.base_url_v1,
        keys=[("Primary", "key-a", 10), ("Secondary", "key-b", 20)],
    )
    _test(client, connection)
    _configure(client, connection, task="ocr_cleanup", model_id="text-large")
    stub_ai.state.failures["key-a"] = ("once", 401)
    stub_ai.state.auth_headers.clear()

    response = client.post("/api/ai/routes/ocr_cleanup/x", json={})
    # The route above is not a real endpoint; use the router directly through
    # a cleanup request instead.
    _ = response

    from app.services import ai_router

    with _session() as session:
        reply = ai_router.complete(
            session,
            "ocr_cleanup",
            system_prompt="clean",
            user_text="Some OCR text",
        )
    assert reply.text == "Cleaned text"
    assert stub_ai.state.auth_headers[-2:] == ["Bearer key-a", "Bearer key-b"]

    keys = client.get(f"/api/ai/connections/{connection['id']}/keys").json()
    assert keys[0]["auth_failed"] is True
    assert keys[1]["status"] == "ready"


def _session():
    from app.db.session import get_session_factory

    return get_session_factory()()


def test_rate_limit_sets_cooldown_and_respects_retry_after(
    client: TestClient, stub_ai
) -> None:
    connection = _create_connection(
        client,
        base_url=stub_ai.base_url_v1,
        keys=[("Primary", "key-a", 10), ("Secondary", "key-b", 20)],
    )
    _test(client, connection)
    _configure(client, connection, task="ocr_cleanup", model_id="text-large")
    stub_ai.state.failures["key-a"] = ("once", 429)
    from app.services import ai_router

    with _session() as session:
        reply = ai_router.complete(
            session, "ocr_cleanup", system_prompt="clean", user_text="Text"
        )
    assert reply.text == "Cleaned text"
    keys = client.get(f"/api/ai/connections/{connection['id']}/keys").json()
    primary = next(item for item in keys if item["label"] == "Primary")
    assert primary["status"] == "rate_limited"
    assert primary["cooldown_until"] is not None
    assert primary["last_error_code"] == "ai_rate_limited"


def test_all_keys_rate_limited_reports_429_without_new_request(
    client: TestClient, stub_ai
) -> None:
    connection = _create_connection(
        client,
        base_url=stub_ai.base_url_v1,
        keys=[("Primary", "key-a", 10)],
    )
    _test(client, connection)
    _configure(client, connection, task="ocr_cleanup", model_id="text-large")
    stub_ai.state.failures["key-a"] = ("once", 429)
    from app.services import ai_router

    with _session() as session:
        with pytest.raises(Exception) as first:
            ai_router.complete(
                session, "ocr_cleanup", system_prompt="clean", user_text="Text"
            )
    assert getattr(first.value, "code", None) == "ai_rate_limited"
    before = len(stub_ai.state.paths)
    with _session() as session:
        with pytest.raises(Exception) as second:
            ai_router.complete(
                session, "ocr_cleanup", system_prompt="clean", user_text="Text"
            )
    assert getattr(second.value, "code", None) == "ai_rate_limited"
    assert len(stub_ai.state.paths) == before


def test_vision_route_rejects_text_only_model(client: TestClient, stub_ai) -> None:
    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    response = client.put(
        "/api/ai/routes/region_proposals",
        json={"connection_id": connection["id"], "model_id": "text-large"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ai_model_missing_vision"


def test_paid_connection_requires_confirmation(client: TestClient, stub_ai) -> None:
    from app.db.models import AiConnection
    from app.services import ai_router

    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    _configure(client, connection, task="ocr_cleanup", model_id="text-large")
    with _session() as session:
        row = session.get(AiConnection, connection["id"])
        row.cost_class = "paid"
        session.commit()

    with _session() as session:
        with pytest.raises(Exception) as refused:
            ai_router.complete(
                session, "ocr_cleanup", system_prompt="clean", user_text="Text"
            )
    assert getattr(refused.value, "code", None) == "ai_paid_confirmation_required"

    with _session() as session:
        reply = ai_router.complete(
            session,
            "ocr_cleanup",
            system_prompt="clean",
            user_text="Text",
            confirm_paid=True,
        )
    assert reply.text == "Cleaned text"


def test_connection_limit_is_recorded_in_usage(client: TestClient, stub_ai) -> None:
    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    _configure(
        client, connection, task="ocr_cleanup", model_id="text-large", request_limit=1
    )
    from app.services import ai_router

    with _session() as session:
        ai_router.complete(
            session, "ocr_cleanup", system_prompt="clean", user_text="One"
        )
    with _session() as session:
        with pytest.raises(Exception) as blocked:
            ai_router.complete(
                session, "ocr_cleanup", system_prompt="clean", user_text="Two"
            )
    assert getattr(blocked.value, "code", None) == "ai_task_limit_reached"

    usage = client.get("/api/ai/usage").json()
    assert usage["used"] == 1
    assert usage["successful"] == 1
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 20
    assert usage["total_tokens"] == 30
    assert usage["estimated_cost_usd"] == pytest.approx(0.00005)
    assert usage["by_connection"][0]["connection_id"] == connection["id"]


def test_clearup_end_to_end_review_accepts_through_byok(
    client: TestClient, project: dict, stub_ai, monkeypatch
) -> None:
    page, run = _ocr_page(client, project, monkeypatch, "page.png")
    block = run["blocks"][0]
    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    _configure(client, connection, task="ocr_cleanup", model_id="text-large")

    response = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr/blocks/{block['id']}/ai-suggestions",
        json={},
    )
    assert response.status_code == 201, response.text
    suggestion = response.json()["suggestion"]
    assert suggestion["proposed_text"] == "Cleaned text"
    assert suggestion["provider"] == "openai_compatible"
    assert suggestion["status"] == "pending"

    accepted = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    page_ocr = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr"
    ).json()
    assert any(item["text"] == "Cleaned text" for item in page_ocr["blocks"])


def test_region_proposals_end_to_end(
    client: TestClient, project: dict, stub_ai, monkeypatch
) -> None:
    page = upload_pages(client, project["id"], ["page.png"])[0]
    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    _configure(
        client, connection, task="region_proposals", model_id="vision-large"
    )
    response = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ai-region-proposals",
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposals"][0]["kind"] == "figure"
    assert body["proposals"][0]["caption"] == "Figure 1"
    usage = client.get("/api/ai/usage").json()
    assert usage["by_task"][0]["task"] == "region_proposals"


def test_unsafe_endpoints_are_rejected(client: TestClient) -> None:
    cases = [
        ("https://169.254.169.254/v1", "ai_url_not_allowed"),
        ("https://user:secret@example.com/v1", "ai_url_not_allowed"),
        ("http://example.com/v1", "ai_remote_not_allowed"),
    ]
    for base_url, code in cases:
        response = client.post(
            "/api/ai/connections",
            json={"provider": "openai_compatible", "base_url": base_url},
        )
        assert response.status_code in {403, 422}, response.text
        assert response.json()["detail"]["code"] == code


def test_remote_requires_https_and_consent(client: TestClient) -> None:
    response = client.post(
        "/api/ai/connections",
        json={
            "provider": "openai",
            "base_url": "http://api.openai.com/v1",
            "allow_remote": True,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ai_https_required"

    response = client.post(
        "/api/ai/connections",
        json={"provider": "openai", "base_url": "https://api.openai.com/v1"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ai_remote_not_allowed"


def test_delete_connection_removes_secrets_and_route(
    client: TestClient, stub_ai
) -> None:
    from app.core.config import get_settings

    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    _configure(client, connection, task="ocr_cleanup", model_id="text-large")
    secret_file = get_settings().data_dir / "secrets" / "ai_keys.enc"
    assert secret_file.exists()

    response = client.delete(f"/api/ai/connections/{connection['id']}")
    assert response.status_code == 200
    assert client.get(f"/api/ai/connections/{connection['id']}").status_code == 404
    route = next(
        item
        for item in client.get("/api/ai/routes").json()["routes"]
        if item["task"] == "ocr_cleanup"
    )
    assert route["connection_id"] is None
    assert b"key-a" not in secret_file.read_bytes()


def test_legacy_settings_migrate_without_duplicates(client: TestClient, tmp_path) -> None:
    from app.db.models import AppSetting, AiConnection
    from app.db.session import get_session_factory
    from app.services import ai_migrate, ai_secrets

    legacy = {
        "text": {
            "provider": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "qwen2.5:7b",
            "allow_remote": False,
            "cost_class": "local",
        },
        "vision": {
            "provider": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "llava:7b",
            "allow_remote": False,
            "cost_class": "local",
            "region_model": "llava:7b",
        },
        "request_limit": 5,
    }
    ai_secrets.set_api_key("text", "legacy-text-key")
    ai_secrets.set_api_key("vision", "legacy-vision-key")
    with get_session_factory()() as session:
        row = session.get(AppSetting, "app")
        if row is None:
            session.add(AppSetting(key="app", value={"language": "en", "ai": legacy}))
        else:
            row.value = {**(row.value or {}), "ai": legacy}
        marker = session.get(AppSetting, "ai_migration")
        if marker is not None:
            session.delete(marker)
        session.commit()

    with get_session_factory()() as session:
        result = ai_migrate.run_legacy_ai_migration(session)
    assert result["status"] == "done"
    assert result["connections"] >= 1

    with get_session_factory()() as session:
        connections = session.query(AiConnection).all()
        count = len(connections)
        assert count == 1
        app_row = session.get(AppSetting, "app")
        assert "ai" not in app_row.value
        assert session.get(AppSetting, "legacy_ai_settings_backup") is not None
    with get_session_factory()() as session:
        ai_migrate.run_legacy_ai_migration(session)
    with get_session_factory()() as session:
        assert session.query(AiConnection).count() == count

    routes = client.get("/api/ai/routes").json()["routes"]
    cleanup = next(item for item in routes if item["task"] == "ocr_cleanup")
    assert cleanup["configured"] is True
    assert cleanup["model_id"] == "qwen2.5:7b"
    keys = client.get(
        f"/api/ai/connections/{cleanup['connection_id']}/keys"
    ).json()
    assert len(keys) == 2
    assert all(item["has_secret"] for item in keys)


def test_discovered_model_search_filters_and_favorites(
    client: TestClient, stub_ai
) -> None:
    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    vision = client.get(
        "/api/ai/models", params={"capability": "vision"}
    ).json()
    assert [item["model_id"] for item in vision] == ["vision-large"]
    text = client.get(
        "/api/ai/models", params={"query": "text"}
    ).json()
    assert [item["model_id"] for item in text] == ["text-large"]

    favorite = client.post(
        f"/api/ai/connections/{connection['id']}/models/favorite",
        json={"model_id": "text-large", "favorite": True},
    )
    assert favorite.status_code == 200, favorite.text
    favorites = client.get(
        "/api/ai/models", params={"favorites_only": True}
    ).json()
    assert [item["model_id"] for item in favorites] == ["text-large"]
