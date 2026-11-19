from __future__ import annotations

import json
import socket
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
        self.ollama_content = "Chapter One (cleaned)"
        self.openai_content = "Chapter One (cleaned)"
        self.vision_content = json.dumps(
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
        self.invalid_tags = False
        self.requests: list[tuple[str, str]] = []
        self.authorization: list[str | None] = []
        self.last_payload: dict | None = None
        # When set, every stub request fails with this status so provider
        # error handling can be tested without a real rate limit.
        self.fail_status: int | None = None
        self.retry_after: str | None = None


def _stub_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict,
    retry_after: str | None = None,
) -> None:
    raw = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    if retry_after is not None:
        handler.send_header("Retry-After", retry_after)
    handler.end_headers()
    handler.wfile.write(raw)


@pytest.fixture()
def stub_ai():
    """A minimal Ollama/OpenAI-compatible server bound to loopback only."""
    state = _StubState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:  # keep pytest output clean
            return

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            state.requests.append(("GET", self.path))
            state.authorization.append(self.headers.get("Authorization"))
            if state.fail_status is not None:
                _stub_response(
                    self, state.fail_status, {"error": "stub failure"}, state.retry_after
                )
                return
            if self.path == "/api/tags":
                if state.invalid_tags:
                    _stub_response(self, 200, {"unexpected": []})
                else:
                    _stub_response(
                        self,
                        200,
                        {
                            "models": [
                                {
                                    "name": "qwen2.5:7b",
                                    "model": "qwen2.5:7b",
                                    "details": {
                                        "family": "qwen2",
                                        "parameter_size": "7B",
                                    },
                                },
                                {"name": "llama3.2:3b", "model": "llama3.2:3b"},
                            ]
                        },
                    )
            elif self.path == "/api/version":
                _stub_response(self, 200, {"version": "0.5.1"})
            elif self.path == "/v1/models":
                _stub_response(
                    self,
                    200,
                    {"data": [{"id": "local-model"}, {"id": "other-model"}]},
                )
            else:
                _stub_response(self, 404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body or b"{}")
            except json.JSONDecodeError:
                _stub_response(self, 400, {"error": "invalid json"})
                return
            state.requests.append(("POST", self.path))
            state.authorization.append(self.headers.get("Authorization"))
            state.last_payload = payload
            if state.fail_status is not None:
                _stub_response(
                    self, state.fail_status, {"error": "stub failure"}, state.retry_after
                )
                return
            assert payload["messages"][0]["role"] == "system"
            user_message = payload["messages"][-1]
            is_vision = bool(user_message.get("images")) or isinstance(
                user_message.get("content"), list
            )
            if self.path == "/api/chat":
                content = state.vision_content if is_vision else state.ollama_content
                _stub_response(
                    self,
                    200,
                    {"message": {"role": "assistant", "content": content}},
                )
            elif self.path == "/v1/chat/completions":
                content = state.vision_content if is_vision else state.openai_content
                _stub_response(
                    self,
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": content,
                                }
                            }
                        ]
                    },
                )
            else:
                _stub_response(self, 404, {"error": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    yield SimpleNamespace(
        base_url=base,
        base_url_v1=f"{base}/v1",
        state=state,
    )
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _closed_port_url() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"


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


def _configure_ai(
    client: TestClient,
    *,
    provider: str = "ollama",
    base_url: str,
    model: str = "qwen2.5:7b",
    allow_remote: bool = False,
    vision_model: str | None = None,
) -> None:
    ai: dict = {
        "text": {
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "allow_remote": allow_remote,
        }
    }
    if vision_model is not None:
        # Vision is a separate task profile; the older helper keeps the same
        # server as text and only swaps the model, which is what the settings
        # migration does for pre-existing installations.
        ai["vision"] = {
            "provider": provider,
            "base_url": base_url,
            "model": vision_model,
            "allow_remote": allow_remote,
        }
    response = client.patch("/api/settings", json={"ai": ai})
    assert response.status_code == 200, response.text


def _suggest(
    client: TestClient, project_id: str, page_id: str, block_id: str, payload: dict | None = None
):
    return client.post(
        f"/api/projects/{project_id}/pages/{page_id}/ocr/blocks/{block_id}/ai-suggestions",
        json=payload or {},
    )


def _usage(client: TestClient) -> dict:
    response = client.get("/api/ai/usage")
    assert response.status_code == 200, response.text
    return response.json()


def test_ai_providers_catalog(client: TestClient) -> None:
    body = client.get("/api/ai/providers").json()
    providers = {item["id"]: item["default_base_url"] for item in body["providers"]}
    assert providers == {
        "ollama": "http://127.0.0.1:11434",
        "openai_compatible": "http://127.0.0.1:1234/v1",
    }


def test_probe_ollama_discovers_models_and_version(
    client: TestClient, stub_ai
) -> None:
    response = client.post(
        "/api/ai/probe",
        json={"provider": "ollama", "base_url": stub_ai.base_url},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["base_url"] == stub_ai.base_url
    assert body["version"] == "0.5.1"
    assert [model["id"] for model in body["models"]] == ["llama3.2:3b", "qwen2.5:7b"]
    assert body["models"][1]["parameter_size"] == "7B"
    assert body["error_code"] is None


def test_probe_openai_compatible_discovers_models(
    client: TestClient, stub_ai
) -> None:
    response = client.post(
        "/api/ai/probe",
        json={"provider": "openai_compatible", "base_url": f"{stub_ai.base_url}/v1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert [model["id"] for model in body["models"]] == ["local-model", "other-model"]


def test_probe_reports_unreachable(client: TestClient, monkeypatch) -> None:
    from urllib.error import URLError

    from app.services import ai as ai_service

    def refuse(*_args, **_kwargs):
        raise URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(ai_service.urllib_request, "urlopen", refuse)
    body = client.post(
        "/api/ai/probe",
        json={"provider": "ollama", "base_url": "http://127.0.0.1:11434"},
    ).json()
    assert body["status"] == "unreachable"
    assert body["error_code"] == "ai_unreachable"
    assert body["models"] == []


def test_probe_reports_timeout(client: TestClient, monkeypatch) -> None:
    from app.services import ai as ai_service

    def hang(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(ai_service.urllib_request, "urlopen", hang)
    body = client.post(
        "/api/ai/probe",
        json={"provider": "ollama", "base_url": "http://127.0.0.1:11434"},
    ).json()
    assert body["status"] == "timeout"
    assert body["error_code"] == "ai_timeout"


def test_probe_reports_http_and_invalid_responses(
    client: TestClient, stub_ai
) -> None:
    http_error = client.post(
        "/api/ai/probe",
        json={"provider": "ollama", "base_url": f"{stub_ai.base_url}/missing"},
    ).json()
    assert http_error["status"] == "http_error"
    assert http_error["error_code"] == "ai_http_error"
    assert http_error["http_status"] == 404

    stub_ai.state.invalid_tags = True
    invalid = client.post(
        "/api/ai/probe",
        json={"provider": "ollama", "base_url": stub_ai.base_url},
    ).json()
    assert invalid["status"] == "invalid_response"
    assert invalid["error_code"] == "ai_invalid_response"


def test_probe_rejects_unsafe_or_credentialed_urls(client: TestClient) -> None:
    for url in (
        "ftp://127.0.0.1:11434",
        "http://user:secret@127.0.0.1:11434",
        "http://169.254.169.254",
        "http://metadata.google.internal",
    ):
        response = client.post(
            "/api/ai/probe",
            json={"provider": "ollama", "base_url": url},
        )
        assert response.status_code == 422, url
        assert response.json()["detail"]["code"] == "invalid_ai_settings"


def test_probe_requires_consent_for_non_loopback_url(client: TestClient, monkeypatch) -> None:
    from urllib.error import URLError

    from app.services import ai as ai_service

    calls: list[str] = []

    def refuse(*_args, **_kwargs):
        calls.append("called")
        raise URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(ai_service.urllib_request, "urlopen", refuse)

    blocked = client.post(
        "/api/ai/probe",
        json={"provider": "ollama", "base_url": "http://192.0.2.10:11434"},
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["detail"]["code"] == "ai_remote_not_allowed"
    # No connection may be attempted before the user consents.
    assert calls == []

    allowed = client.post(
        "/api/ai/probe",
        json={
            "provider": "ollama",
            "base_url": "http://192.0.2.10:11434",
            "allow_remote": True,
        },
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "unreachable"
    assert calls == ["called"]


def test_normalize_base_url_treats_loopback_as_local() -> None:
    from app.core.errors import AppError
    from app.services.ai import normalize_base_url

    for host in ("127.0.0.1", "localhost", "app.localhost", "[::1]"):
        assert normalize_base_url("ollama", f"http://{host}:11434") == (
            f"http://{host}:11434"
        )
    with pytest.raises(AppError) as error:
        normalize_base_url("ollama", "http://192.0.2.10:11434")
    assert error.value.code == "ai_remote_not_allowed"


def test_ai_profile_settings_validation_and_persistence(client: TestClient) -> None:
    ai_settings = client.get("/api/settings").json()["ai"]
    assert ai_settings["request_limit"] == 0
    defaults = ai_settings["text"]
    assert defaults == {
        "provider": "ollama",
        "base_url": "",
        "model": "",
        "allow_remote": False,
        "cost_class": "local",
        "has_api_key": False,
    }
    # Image analysis has its own provider, URL, model and consent.
    assert ai_settings["vision"] == defaults

    saved = client.patch(
        "/api/settings",
        json={"ai": {"text": {"provider": "openai_compatible", "model": " local-model "}}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ai"]["text"] == {
        "provider": "openai_compatible",
        "base_url": "",
        "model": "local-model",
        "allow_remote": False,
        "cost_class": "local",
        "has_api_key": False,
    }

    consented = client.patch(
        "/api/settings",
        json={"ai": {"text": {"base_url": "http://192.0.2.10:1234", "allow_remote": True}}},
    )
    assert consented.status_code == 200, consented.text
    assert consented.json()["ai"]["text"] == {
        "provider": "openai_compatible",
        "base_url": "http://192.0.2.10:1234",
        "model": "local-model",
        "allow_remote": True,
        # A remote URL cannot stay classified as local inference.
        "cost_class": "paid",
        "has_api_key": False,
    }

    limited = client.patch("/api/settings", json={"ai": {"request_limit": 25}})
    assert limited.status_code == 200, limited.text
    assert limited.json()["ai"]["request_limit"] == 25
    assert client.get("/api/ai/usage").json()["request_limit"] == 25

    vision_saved = client.patch(
        "/api/settings",
        json={"ai": {"vision": {"provider": "ollama", "model": " llava:7b "}}},
    )
    assert vision_saved.status_code == 200, vision_saved.text
    assert vision_saved.json()["ai"]["vision"] == {
        "provider": "ollama",
        "base_url": "",
        "model": "llava:7b",
        "allow_remote": False,
        "cost_class": "local",
        "has_api_key": False,
    }
    # Saving the vision profile never changes the text profile.
    assert vision_saved.json()["ai"]["text"]["provider"] == "openai_compatible"
    assert vision_saved.json()["ai"]["text"]["model"] == "local-model"

    for bad in (
        {"base_url": "ftp://127.0.0.1:1234"},
        {"base_url": "http://user:secret@127.0.0.1:1234"},
        {"model": "x" * 201},
    ):
        response = client.patch("/api/settings", json={"ai": {"text": bad}})
        assert response.status_code == 422, bad
        response = client.patch("/api/settings", json={"ai": {"vision": bad}})
        assert response.status_code == 422, bad

    for bad_limit in (-1, 10_001):
        response = client.patch("/api/settings", json={"ai": {"request_limit": bad_limit}})
        assert response.status_code == 422, bad_limit


def test_api_keys_are_write_only_and_encrypted(client: TestClient) -> None:
    from app.core.config import get_settings

    saved = client.patch(
        "/api/settings",
        json={
            "ai": {
                "text": {
                    "provider": "openai_compatible",
                    "api_key": "  sk-text-secret  ",
                }
            }
        },
    )
    assert saved.status_code == 200, saved.text
    profile = saved.json()["ai"]["text"]
    assert profile["has_api_key"] is True
    assert "api_key" not in profile
    assert "sk-text-secret" not in saved.text
    assert client.get("/api/settings").json()["ai"]["text"]["has_api_key"] is True

    # The key is encrypted at rest; neither file contains the plain value.
    secrets_dir = get_settings().data_dir / "secrets"
    store = (secrets_dir / "ai_keys.enc").read_bytes()
    master = (secrets_dir / "ai_keys.key").read_bytes()
    assert b"sk-text-secret" not in store
    assert b"sk-text-secret" not in master

    vision = client.patch(
        "/api/settings",
        json={"ai": {"vision": {"api_key": "vk-vision-secret"}}},
    )
    assert vision.status_code == 200, vision.text
    assert vision.json()["ai"]["vision"]["has_api_key"] is True
    # Each task profile keeps its own key.
    assert vision.json()["ai"]["text"]["has_api_key"] is True

    cleared = client.patch(
        "/api/settings", json={"ai": {"text": {"clear_api_key": True}}}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["ai"]["text"]["has_api_key"] is False
    assert cleared.json()["ai"]["vision"]["has_api_key"] is True
    assert client.get("/api/settings").json()["ai"]["text"]["has_api_key"] is False

    for bad in ("", "   ", "two words", "x" * 1025, "ключ", "sk-\t1"):
        response = client.patch("/api/settings", json={"ai": {"text": {"api_key": bad}}})
        assert response.status_code == 422, bad

    both = client.patch(
        "/api/settings",
        json={"ai": {"vision": {"api_key": "vk-next", "clear_api_key": True}}},
    )
    assert both.status_code == 422, both.text


def test_corrupt_key_store_degrades_to_no_key(client: TestClient) -> None:
    from app.core.config import get_settings

    secrets_dir = get_settings().data_dir / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "ai_keys.enc").write_bytes(b"not-a-fernet-token")

    response = client.get("/api/settings")
    assert response.status_code == 200, response.text
    assert response.json()["ai"]["text"]["has_api_key"] is False
    assert response.json()["ai"]["vision"]["has_api_key"] is False

    # Saving a new key rewrites the store instead of staying blocked.
    saved = client.patch(
        "/api/settings", json={"ai": {"text": {"api_key": "sk-recovered"}}}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ai"]["text"]["has_api_key"] is True


def test_saved_key_reaches_only_the_saved_server(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(
        client,
        provider="openai_compatible",
        base_url=stub_ai.base_url_v1,
        model="local-model",
    )
    saved = client.patch(
        "/api/settings", json={"ai": {"text": {"api_key": "sk-live"}}}
    )
    assert saved.status_code == 200, saved.text

    page, run = _ocr_page(client, project, monkeypatch, "ai-key-header.png")
    cleanup = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert cleanup.status_code == 201, cleanup.text
    assert stub_ai.state.authorization[-1] == "Bearer sk-live"

    # A probe can reuse the saved key for the same task profile.
    probe = client.post(
        "/api/ai/probe",
        json={
            "provider": "openai_compatible",
            "base_url": stub_ai.base_url_v1,
            "task": "text",
        },
    )
    assert probe.status_code == 200, probe.text
    assert probe.json()["status"] == "ready"
    assert stub_ai.state.authorization[-1] == "Bearer sk-live"

    # Reusing the saved key requires the same saved server. A different host
    # string, even pointing at the same machine, must not receive it.
    other_host = client.post(
        "/api/ai/probe",
        json={
            "provider": "openai_compatible",
            "base_url": stub_ai.base_url_v1.replace("127.0.0.1", "localhost"),
            "task": "text",
        },
    )
    assert other_host.status_code == 200, other_host.text
    assert other_host.json()["status"] == "ready"
    assert stub_ai.state.authorization[-1] is None

    # A per-request server override must never receive the stored key.
    override = _suggest(
        client,
        project["id"],
        page["id"],
        run["blocks"][0]["id"],
        {
            "provider": "openai_compatible",
            "base_url": stub_ai.base_url_v1,
            "model": "local-model",
        },
    )
    assert override.status_code == 201, override.text
    assert stub_ai.state.authorization[-1] is None

    # The usage ledger records metadata only, never the credential.
    assert "sk-live" not in client.get("/api/ai/usage/history").text


def test_cleanup_requires_a_configured_model(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _ocr_page(client, project, monkeypatch, "ai-unconfigured.png")
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ai_not_configured"
    # Validation failures never contacted a provider, so they are not counted.
    assert _usage(client)["used"] == 0


def test_cleanup_requires_consent_for_non_loopback_server(
    client: TestClient, project: dict, monkeypatch
) -> None:
    _configure_ai(client, base_url="http://192.0.2.10:11434")
    page, run = _ocr_page(client, project, monkeypatch, "ai-remote-consent.png")
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "ai_remote_not_allowed"
    assert _usage(client)["used"] == 0


def test_cleanup_records_usage_and_enforces_rolling_limit(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-usage.png")

    # Connection tests are not charged against the request limit.
    probe = client.post(
        "/api/ai/probe",
        json={"provider": "ollama", "base_url": stub_ai.base_url},
    )
    assert probe.status_code == 200
    empty = _usage(client)
    assert empty["used"] == 0
    assert empty["recent"] == []
    assert empty["by_task"] == []
    assert empty["request_limit"] == 0
    assert empty["remaining"] is None

    created = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert created.status_code == 201, created.text
    after_success = _usage(client)
    assert after_success["used"] == 1
    assert after_success["successful"] == 1
    assert after_success["failed"] == 0
    assert after_success["by_task"] == [{"task": "ocr_cleanup", "used": 1}]
    entry = after_success["recent"][0]
    assert entry["outcome"] == "success"
    assert entry["provider"] == "ollama"
    assert entry["model"] == "qwen2.5:7b"
    assert entry["task"] == "ocr_cleanup"
    assert entry["project_id"] == project["id"]
    assert entry["page_id"] == page["id"]
    assert entry["block_id"] == run["blocks"][0]["id"]

    # A provider request that fails still counts, because it used the server.
    _configure_ai(client, base_url=_closed_port_url())
    failed = _suggest(client, project["id"], page["id"], run["blocks"][1]["id"])
    assert failed.status_code == 502, failed.text
    assert failed.json()["detail"]["code"] == "ai_unreachable"
    after_failure = _usage(client)
    assert after_failure["used"] == 2
    assert after_failure["successful"] == 1
    assert after_failure["failed"] == 1
    assert after_failure["recent"][0]["outcome"] == "error"
    assert after_failure["recent"][0]["error_code"] == "ai_unreachable"

    limited = client.patch("/api/settings", json={"ai": {"request_limit": 2}})
    assert limited.status_code == 200, limited.text
    blocked = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["detail"]["code"] == "ai_request_limit_reached"
    after_block = _usage(client)
    assert after_block["used"] == 2
    assert after_block["request_limit"] == 2
    assert after_block["remaining"] == 0

    # Raising the cap immediately allows another request.
    raised = client.patch("/api/settings", json={"ai": {"request_limit": 3}})
    assert raised.status_code == 200
    _configure_ai(client, base_url=stub_ai.base_url)
    allowed = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert allowed.status_code == 201, allowed.text
    assert _usage(client)["used"] == 3


def test_usage_breakdown_counts_tasks_in_a_stable_order(
    client: TestClient, project: dict
) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for task in ("equation_transcription", "ocr_cleanup", "ocr_cleanup"):
        _insert_usage(
            model="qwen2.5:7b",
            task=task,
            outcome="success",
            created_at=now,
            project_id=project["id"],
        )
    # A stored name this build does not know must still be counted and shown
    # instead of disappearing from the budget it consumed.
    _insert_usage(
        model="qwen2.5:7b",
        task="legacy_task",
        outcome="error",
        error_code="ai_unreachable",
        created_at=now,
        project_id=project["id"],
    )

    body = _usage(client)
    assert body["used"] == 4
    # Errors consume the budget, so the failed attempt is included.
    assert body["by_task"] == [
        {"task": "ocr_cleanup", "used": 2},
        {"task": "equation_transcription", "used": 1},
        {"task": "legacy_task", "used": 1},
    ]


def test_page_suggestions_can_be_listed_and_filtered(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page_a, run_a = _ocr_page(client, project, monkeypatch, "ai-list-a.png")
    page_b, run_b = _ocr_page(client, project, monkeypatch, "ai-list-b.png")

    first = _suggest(client, project["id"], page_a["id"], run_a["blocks"][0]["id"]).json()[
        "suggestion"
    ]
    second = _suggest(client, project["id"], page_a["id"], run_a["blocks"][1]["id"]).json()[
        "suggestion"
    ]
    third = _suggest(client, project["id"], page_b["id"], run_b["blocks"][0]["id"]).json()[
        "suggestion"
    ]
    decided = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{first['id']}",
        json={"status": "accepted"},
    )
    assert decided.status_code == 200, decided.text

    all_a = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions"
    )
    assert all_a.status_code == 200, all_a.text
    assert {item["id"] for item in all_a.json()["suggestions"]} == {
        first["id"],
        second["id"],
    }

    accepted = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"status": "accepted"},
    ).json()["suggestions"]
    assert [item["id"] for item in accepted] == [first["id"]]
    assert accepted[0]["status"] == "accepted"
    assert accepted[0]["original_text"] == "Chapter One"
    assert accepted[0]["proposed_text"] == "Chapter One (cleaned)"

    pending = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"status": "pending"},
    ).json()["suggestions"]
    assert [item["id"] for item in pending] == [second["id"]]

    rejected = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"status": "rejected"},
    ).json()["suggestions"]
    assert rejected == []

    # Proposals stay scoped to the page that produced them.
    other_page = client.get(
        f"/api/projects/{project['id']}/pages/{page_b['id']}/ai-suggestions"
    ).json()["suggestions"]
    assert [item["id"] for item in other_page] == [third["id"]]

    limited = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"limit": 1},
    ).json()["suggestions"]
    assert [item["id"] for item in limited] == [second["id"]]

    for bad_limit in (0, 501):
        response = client.get(
            f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
            params={"limit": bad_limit},
        )
        assert response.status_code == 422, bad_limit

    invalid = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"status": "unknown"},
    )
    assert invalid.status_code == 422

    missing = client.get(
        f"/api/projects/{project['id']}/pages/unknown-page/ai-suggestions"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "page_not_found"

    # The project-wide queue spans pages and reports the page number for each row.
    project_all = client.get(
        f"/api/projects/{project['id']}/ai-suggestions"
    ).json()["suggestions"]
    assert {item["id"] for item in project_all} == {first["id"], second["id"], third["id"]}
    by_id = {item["id"]: item for item in project_all}
    assert by_id[first["id"]]["page_number"] == page_a["page_number"]
    assert by_id[third["id"]]["page_number"] == page_b["page_number"]

    project_pending = client.get(
        f"/api/projects/{project['id']}/ai-suggestions",
        params={"status": "pending"},
    ).json()["suggestions"]
    assert {item["id"] for item in project_pending} == {second["id"], third["id"]}

    project_limited = client.get(
        f"/api/projects/{project['id']}/ai-suggestions",
        params={"limit": 1},
    ).json()["suggestions"]
    assert [item["id"] for item in project_limited] == [third["id"]]

    invalid_project = client.get(
        f"/api/projects/{project['id']}/ai-suggestions",
        params={"status": "unknown"},
    )
    assert invalid_project.status_code == 422


def test_cleanup_suggestion_is_reviewable_and_accepting_updates_text(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-cleanup.png")
    block = run["blocks"][0]

    created = _suggest(client, project["id"], page["id"], block["id"])
    assert created.status_code == 201, created.text
    body = created.json()
    suggestion = body["suggestion"]
    assert suggestion["status"] == "pending"
    assert suggestion["task"] == "ocr_cleanup"
    assert suggestion["original_text"] == "Chapter One"
    assert suggestion["proposed_text"] == "Chapter One (cleaned)"
    assert suggestion["provider"] == "ollama"
    assert suggestion["model"] == "qwen2.5:7b"
    assert suggestion["base_url"] == stub_ai.base_url
    assert body["run"]["blocks"][0]["text"] == "Chapter One"
    assert ("POST", "/api/chat") in stub_ai.state.requests

    accepted = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    decided = accepted.json()
    assert decided["suggestion"]["status"] == "accepted"
    assert decided["run"]["blocks"][0]["text"] == "Chapter One (cleaned)"
    assert decided["run"]["blocks"][0]["corrected"] is True
    latest = client.get(f"/api/projects/{project['id']}/pages/{page['id']}/ocr").json()
    assert latest["blocks"][0]["text"] == "Chapter One (cleaned)"


def test_cleanup_supports_openai_compatible_override(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(
        client,
        provider="ollama",
        base_url=_closed_port_url(),
        model="qwen2.5:7b",
    )
    page, run = _ocr_page(client, project, monkeypatch, "ai-openai.png")
    created = _suggest(
        client,
        project["id"],
        page["id"],
        run["blocks"][0]["id"],
        {
            "provider": "openai_compatible",
            "base_url": stub_ai.base_url_v1,
            "model": "local-model",
        },
    )
    assert created.status_code == 201, created.text
    suggestion = created.json()["suggestion"]
    assert suggestion["provider"] == "openai_compatible"
    assert suggestion["model"] == "local-model"
    assert suggestion["base_url"] == stub_ai.base_url_v1
    assert ("POST", "/v1/chat/completions") in stub_ai.state.requests


def test_cleanup_rejects_when_ocr_text_changed_after_proposal(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-stale-text.png")
    block = run["blocks"][0]
    suggestion = _suggest(client, project["id"], page["id"], block["id"]).json()["suggestion"]

    edited = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr/blocks/{block['id']}",
        json={"text": "Chapter One (manual)"},
    )
    assert edited.status_code == 200

    accepted = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 409
    assert accepted.json()["detail"]["code"] == "ai_suggestion_stale"

    # Rejecting the obsolete proposal is still possible.
    rejected = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["suggestion"]["status"] == "rejected"
    assert rejected.json()["run"]["blocks"][0]["text"] == "Chapter One (manual)"

    # The reviewed proposal stays available as an audit record, including the
    # original and proposed text from before the manual correction.
    history = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/ai-suggestions"
    ).json()["suggestions"]
    assert [item["status"] for item in history] == ["rejected"]
    assert history[0]["original_text"] == "Chapter One"
    assert history[0]["proposed_text"] == "Chapter One (cleaned)"


def test_cleanup_refuses_a_stale_ocr_run(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-stale-run.png")
    rotated = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/rotate",
        json={"degrees": 90},
    )
    assert rotated.status_code == 200
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_stale"


def test_cleanup_empty_response_is_not_stored(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-empty.png")
    stub_ai.state.ollama_content = "   "
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ai_empty_response"


def test_rejected_suggestion_keeps_text_and_cannot_be_redecided(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-reject.png")
    block = run["blocks"][0]
    suggestion = _suggest(client, project["id"], page["id"], block["id"]).json()["suggestion"]

    rejected = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["run"]["blocks"][0]["text"] == "Chapter One"

    again = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "accepted"},
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "ai_suggestion_not_pending"


def test_bulk_reject_reviews_every_unique_pending_proposal(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-bulk-reject.png")
    first = _suggest(
        client, project["id"], page["id"], run["blocks"][0]["id"]
    ).json()["suggestion"]
    second = _suggest(
        client, project["id"], page["id"], run["blocks"][1]["id"]
    ).json()["suggestion"]

    response = client.post(
        f"/api/projects/{project['id']}/ai-suggestions/bulk",
        json={"ids": [first["id"], second["id"], first["id"]], "status": "rejected"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requested"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    assert [item["id"] for item in body["results"]] == [first["id"], second["id"]]
    assert [item["status"] for item in body["results"]] == ["rejected", "rejected"]
    assert all(item["error_code"] is None for item in body["results"])

    pending = client.get(
        f"/api/projects/{project['id']}/ai-suggestions", params={"status": "pending"}
    ).json()["suggestions"]
    assert pending == []
    rejected = client.get(
        f"/api/projects/{project['id']}/ai-suggestions", params={"status": "rejected"}
    ).json()["suggestions"]
    assert {item["id"] for item in rejected} == {first["id"], second["id"]}

    latest = client.get(f"/api/projects/{project['id']}/pages/{page['id']}/ocr").json()
    assert [block["text"] for block in latest["blocks"]] == [
        "Chapter One",
        "A local OCR result.",
    ]


def test_bulk_accept_skips_stale_proposals_and_reports_each_item(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-bulk-accept.png")
    stale_block = run["blocks"][0]
    fresh_block = run["blocks"][1]
    stale = _suggest(
        client, project["id"], page["id"], stale_block["id"]
    ).json()["suggestion"]
    fresh = _suggest(
        client, project["id"], page["id"], fresh_block["id"]
    ).json()["suggestion"]

    edited = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr/blocks/{stale_block['id']}",
        json={"text": "Manual correction"},
    )
    assert edited.status_code == 200, edited.text

    response = client.post(
        f"/api/projects/{project['id']}/ai-suggestions/bulk",
        json={"ids": [stale["id"], fresh["id"]], "status": "accepted"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requested"] == 2
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    assert body["results"][0] == {
        "id": stale["id"],
        "status": None,
        "error_code": "ai_suggestion_stale",
    }
    assert body["results"][1] == {
        "id": fresh["id"],
        "status": "accepted",
        "error_code": None,
    }

    latest = client.get(f"/api/projects/{project['id']}/pages/{page['id']}/ocr").json()
    assert latest["blocks"][0]["text"] == "Manual correction"
    assert latest["blocks"][1]["text"] == "Chapter One (cleaned)"
    pending = client.get(
        f"/api/projects/{project['id']}/ai-suggestions", params={"status": "pending"}
    ).json()["suggestions"]
    assert [item["id"] for item in pending] == [stale["id"]]

    missing = client.post(
        f"/api/projects/{project['id']}/ai-suggestions/bulk",
        json={"ids": ["missing-id"], "status": "rejected"},
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["failed"] == 1
    assert missing.json()["results"][0]["error_code"] == "ai_suggestion_not_found"

    empty = client.post(
        f"/api/projects/{project['id']}/ai-suggestions/bulk",
        json={"ids": [], "status": "rejected"},
    )
    assert empty.status_code == 422
    oversized = client.post(
        f"/api/projects/{project['id']}/ai-suggestions/bulk",
        json={"ids": [f"id-{index}" for index in range(101)], "status": "rejected"},
    )
    assert oversized.status_code == 422


def test_project_schema_contains_ai_suggestions(client: TestClient, project: dict) -> None:
    from app.db.project_schema import project_db

    with project_db(Path(project["directory"])) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert "ai_suggestions" in tables


def _vision(client: TestClient, project_id: str, page_id: str, payload: dict | None = None):
    return client.post(
        f"/api/projects/{project_id}/pages/{page_id}/ai-region-proposals",
        json=payload or {},
    )


def test_vision_region_proposals_require_a_vision_model(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["ai-vision-unconfigured.png"])[0]
    response = _vision(client, project["id"], page["id"])
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ai_vision_not_configured"
    # Nothing was sent, so nothing is counted.
    assert _usage(client)["used"] == 0


def test_vision_tasks_use_their_own_server_profile(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    closed = _closed_port_url()
    saved = client.patch(
        "/api/settings",
        json={
            "ai": {
                "text": {
                    "provider": "ollama",
                    "base_url": closed,
                    "model": "qwen2.5:7b",
                },
                "vision": {
                    "provider": "ollama",
                    "base_url": stub_ai.base_url,
                    "model": "llava:7b",
                },
            }
        },
    )
    assert saved.status_code == 200, saved.text

    page = upload_pages(client, project["id"], ["ai-vision-separate.png"])[0]
    vision = _vision(client, project["id"], page["id"])
    assert vision.status_code == 200, vision.text
    assert vision.json()["model"] == "llava:7b"
    assert ("POST", "/api/chat") in stub_ai.state.requests

    # The text task keeps using its own unreachable server instead of falling
    # back to the working vision server.
    page, run = _ocr_page(client, project, monkeypatch, "ai-text-separate.png")
    cleanup = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert cleanup.status_code == 502, cleanup.text
    assert cleanup.json()["detail"]["code"] == "ai_unreachable"

    tasks = [(row["task"], row["outcome"]) for row in _usage(client)["recent"]]
    assert ("region_proposals", "success") in tasks
    assert ("ocr_cleanup", "error") in tasks


def test_legacy_vision_model_migrates_to_a_vision_profile(client: TestClient) -> None:
    from app.db.models import AppSetting
    from app.db.session import get_session_factory

    session = get_session_factory()()
    try:
        session.add(
            AppSetting(
                key="app",
                value={
                    "ai": {
                        "text": {
                            "provider": "openai_compatible",
                            "base_url": "http://127.0.0.1:1234/v1",
                            "model": "local-model",
                        },
                        "vision_model": " llava:7b ",
                    }
                },
            )
        )
        session.commit()
    finally:
        session.close()

    migrated = client.get("/api/settings").json()["ai"]
    assert migrated["vision"] == {
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "llava:7b",
        "allow_remote": False,
        "cost_class": "local",
        "has_api_key": False,
    }
    assert "vision_model" not in migrated

    # The legacy key is replaced with the new profile on the next save.
    assert client.patch("/api/settings", json={"language": "en"}).status_code == 200
    session = get_session_factory()()
    try:
        stored = session.get(AppSetting, "app")
        assert stored is not None
        assert "vision_model" not in stored.value["ai"]
        assert stored.value["ai"]["vision"]["model"] == "llava:7b"
    finally:
        session.close()


def test_vision_region_proposals_map_coordinates_and_record_usage(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(
        client,
        base_url=stub_ai.base_url,
        vision_model="llava:7b",
    )
    page = upload_pages(client, project["id"], ["ai-vision.png"])[0]
    response = _vision(client, project["id"], page["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["page_width"] == 1200
    assert body["page_height"] == 800
    assert body["provider"] == "ollama"
    assert body["model"] == "llava:7b"

    proposal = body["proposals"][0]
    assert proposal["kind"] == "figure"
    assert proposal["reason"] == "ai_vision"
    assert proposal["confidence"] == "low"
    assert proposal["caption"] == "Figure 1"
    assert proposal["block_ids"] == []
    # 0.1/0.2/0.3/0.4 of 1200x800, plus the same small padding as heuristic
    # proposals (10px horizontally, 6px vertically).
    assert (proposal["x"], proposal["y"]) == (110, 154)
    assert (proposal["width"], proposal["height"]) == (380, 332)

    payload = stub_ai.state.last_payload
    assert payload is not None
    assert payload["messages"][-1]["images"]

    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["task"] == "region_proposals"
    assert usage["recent"][0]["page_id"] == page["id"]
    assert usage["recent"][0]["block_id"] is None


def test_vision_region_proposals_support_openai_compatible_override(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    page = upload_pages(client, project["id"], ["ai-vision-openai.png"])[0]
    response = _vision(
        client,
        project["id"],
        page["id"],
        {
            "provider": "openai_compatible",
            "base_url": stub_ai.base_url_v1,
            "model": "vision-local",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "openai_compatible"
    assert response.json()["model"] == "vision-local"

    payload = stub_ai.state.last_payload
    assert payload is not None
    content = payload["messages"][-1]["content"]
    assert isinstance(content, list)
    image = next(item for item in content if item["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_vision_region_proposals_drop_unusable_regions(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    page = upload_pages(client, project["id"], ["ai-vision-filter.png"])[0]
    stub_ai.state.vision_content = json.dumps(
        {
            "regions": [
                {"kind": "paragraph", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                {"kind": "table", "x": -0.2, "y": 0.1, "width": 0.2, "height": 0.2},
                {"kind": "figure", "x": 0.9, "y": 0.1, "width": 0.5, "height": 0.2},
                {"kind": "equation", "x": 0.4, "y": 0.4, "width": 0.2, "height": 0.1},
            ]
        }
    )
    response = _vision(client, project["id"], page["id"])
    assert response.status_code == 200, response.text
    proposals = response.json()["proposals"]
    assert [item["kind"] for item in proposals] == ["figure", "equation"]
    assert all(item["caption"] == "" for item in proposals)
    # A box that starts inside the page and runs past the edge is clipped.
    figure = proposals[0]
    assert figure["x"] + figure["width"] <= 1200


def test_vision_region_proposals_report_invalid_output(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    page = upload_pages(client, project["id"], ["ai-vision-invalid.png"])[0]
    stub_ai.state.vision_content = "I could not analyse the image."
    response = _vision(client, project["id"], page["id"])
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "ai_invalid_response"
    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["outcome"] == "error"
    assert usage["recent"][0]["error_code"] == "ai_invalid_response"
    assert usage["recent"][0]["task"] == "region_proposals"


def test_vision_region_proposals_respect_remote_consent_and_limit(
    client: TestClient, project: dict, stub_ai
) -> None:
    page = upload_pages(client, project["id"], ["ai-vision-consent.png"])[0]
    _configure_ai(
        client,
        base_url="http://192.0.2.10:11434",
        vision_model="llava:7b",
    )
    refused = _vision(client, project["id"], page["id"])
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "ai_remote_not_allowed"
    assert _usage(client)["used"] == 0

    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    limited = client.patch("/api/settings", json={"ai": {"request_limit": 1}})
    assert limited.status_code == 200
    first = _vision(client, project["id"], page["id"])
    assert first.status_code == 200, first.text
    blocked = _vision(client, project["id"], page["id"])
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["detail"]["code"] == "ai_request_limit_reached"


def _equation_region(
    client: TestClient, project_id: str, page_id: str, kind: str = "equation"
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/pages/{page_id}/elements",
        json={
            "kind": kind,
            "x": 100,
            "y": 120,
            "width": 300,
            "height": 120,
            "caption": "",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _equation(
    client: TestClient, project_id: str, element_id: str, payload: dict | None = None
):
    return client.post(
        f"/api/projects/{project_id}/elements/{element_id}/ai-equation",
        json=payload or {},
    )


def test_equation_transcription_requires_a_vision_model(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["ai-equation-unconfigured.png"])[0]
    element = _equation_region(client, project["id"], page["id"])
    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ai_vision_not_configured"
    assert _usage(client)["used"] == 0


def test_equation_transcription_returns_a_reviewable_proposal(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    stub_ai.state.vision_content = "E = mc^{2}"
    page = upload_pages(client, project["id"], ["ai-equation.png"])[0]
    element = _equation_region(client, project["id"], page["id"])

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["latex"] == "E = mc^{2}"
    assert body["provider"] == "ollama"
    assert body["model"] == "llava:7b"
    assert body["element_id"] == element["id"]
    assert body["page_id"] == page["id"]

    payload = stub_ai.state.last_payload
    assert payload is not None
    # The saved vision model is used, not the text model, and the crop is inline.
    assert payload["model"] == "llava:7b"
    assert payload["messages"][-1]["images"]
    # LaTeX is requested as plain text, so JSON mode must stay off.
    assert "format" not in payload

    # The proposal is not written anywhere: the element still has no text.
    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    )
    assert listed.json()[0]["text"] == ""

    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["task"] == "equation_transcription"
    assert usage["recent"][0]["page_id"] == page["id"]
    assert usage["recent"][0]["block_id"] is None


def test_equation_transcription_strips_model_wrappers(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    stub_ai.state.vision_content = "```latex\n$$\nE = mc^2\n$$\n```"
    page = upload_pages(client, project["id"], ["ai-equation-wrapper.png"])[0]
    element = _equation_region(client, project["id"], page["id"])

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 200, response.text
    assert response.json()["latex"] == "E = mc^2"


def test_equation_transcription_refuses_other_region_kinds(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    page = upload_pages(client, project["id"], ["ai-equation-figure.png"])[0]
    element = _equation_region(client, project["id"], page["id"], kind="figure")

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ai_equation_region_required"
    assert stub_ai.state.requests == []
    assert _usage(client)["used"] == 0


def test_equation_transcription_reports_an_empty_reply(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    stub_ai.state.vision_content = "   "
    page = upload_pages(client, project["id"], ["ai-equation-empty.png"])[0]
    element = _equation_region(client, project["id"], page["id"])

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "ai_equation_empty"
    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["outcome"] == "error"
    assert usage["recent"][0]["error_code"] == "ai_equation_empty"
    assert usage["recent"][0]["task"] == "equation_transcription"


def test_equation_transcription_supports_openai_compatible_override(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    stub_ai.state.vision_content = "\\frac{a}{b}"
    page = upload_pages(client, project["id"], ["ai-equation-openai.png"])[0]
    element = _equation_region(client, project["id"], page["id"])

    response = _equation(
        client,
        project["id"],
        element["id"],
        {
            "provider": "openai_compatible",
            "base_url": stub_ai.base_url_v1,
            "model": "vision-local",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["latex"] == "\\frac{a}{b}"
    assert body["provider"] == "openai_compatible"
    assert body["model"] == "vision-local"

    payload = stub_ai.state.last_payload
    assert payload is not None
    content = payload["messages"][-1]["content"]
    assert isinstance(content, list)
    image = next(item for item in content if item["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_equation_transcription_respects_remote_consent(
    client: TestClient, project: dict
) -> None:
    _configure_ai(
        client,
        base_url="http://192.0.2.10:11434",
        vision_model="llava:7b",
    )
    page = upload_pages(client, project["id"], ["ai-equation-consent.png"])[0]
    element = _equation_region(client, project["id"], page["id"])

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "ai_remote_not_allowed"
    assert _usage(client)["used"] == 0


def test_equation_transcription_rejects_an_unknown_region(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    missing = "00000000-0000-4000-8000-000000000000"
    response = _equation(client, project["id"], missing)
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "element_not_found"
    assert stub_ai.state.requests == []
    assert _usage(client)["used"] == 0


def test_equation_latex_parser_strips_only_wrappers() -> None:
    from app.services.ai import parse_equation_latex

    assert parse_equation_latex("```\n$$x^{2}$$\n```") == "x^{2}"
    assert parse_equation_latex('"\\[ a + b \\]"') == "a + b"
    assert parse_equation_latex("  E = mc^2  ") == "E = mc^2"


def test_table_grid_parser_accepts_only_a_complete_rectangle() -> None:
    from app.core.errors import AppError
    from app.services.ai import parse_table_grid

    assert parse_table_grid('{"rows": [["Item", "Qty"], ["Apples", "3"]]}') == [
        ["Item", "Qty"],
        ["Apples", "3"],
    ]
    assert parse_table_grid('```json\n{"rows": [["1", "2"], ["3", 4]]}\n```') == [
        ["1", "2"],
        ["3", "4"],
    ]
    # A null cell is text the model did not report, so it stays an empty cell.
    assert parse_table_grid('{"rows": [["a", null], ["c", "d"]]}') == [
        ["a", ""],
        ["c", "d"],
    ]

    for reply in (
        "not json",
        '{"rows": []}',
        '{"rows": [["a", "b"], ["c"]]}',
        '{"rows": [["a"], ["b"]]}',
        '{"rows": [["a", ["b"]], ["c", "d"]]}',
        '{"rows": [["a", true], ["c", "d"]]}',
    ):
        with pytest.raises(AppError) as excinfo:
            parse_table_grid(reply)
        assert excinfo.value.status_code == 502

    too_many_rows = json.dumps({"rows": [["a", "b"]] * 61})
    with pytest.raises(AppError) as excinfo:
        parse_table_grid(too_many_rows)
    assert excinfo.value.code == "ai_table_too_large"


def _table(
    client: TestClient, project_id: str, element_id: str, payload: dict | None = None
):
    return client.post(
        f"/api/projects/{project_id}/elements/{element_id}/ai-table",
        json=payload or {},
    )


def test_ai_table_requires_a_table_region_and_vision_model(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    page = upload_pages(client, project["id"], ["ai-table-kind.png"])[0]
    figure = _equation_region(client, project["id"], page["id"], kind="figure")
    refused = _table(client, project["id"], figure["id"])
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "ai_table_region_required"
    assert _usage(client)["used"] == 0

    table_region = _equation_region(client, project["id"], page["id"], kind="table")
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="")
    unconfigured = _table(client, project["id"], table_region["id"])
    assert unconfigured.status_code == 409, unconfigured.text
    assert unconfigured.json()["detail"]["code"] == "ai_vision_not_configured"
    assert _usage(client)["used"] == 0


def test_ai_table_returns_a_reviewable_grid(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    stub_ai.state.vision_content = json.dumps(
        {"rows": [["Item", "Qty"], ["Apples", "3"], ["Pears", ""]]}
    )
    page = upload_pages(client, project["id"], ["ai-table.png"])[0]
    element = _equation_region(client, project["id"], page["id"], kind="table")

    response = _table(client, project["id"], element["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["element_id"] == element["id"]
    assert body["page_id"] == page["id"]
    assert body["provider"] == "ollama"
    assert body["model"] == "llava:7b"
    assert body["rows"] == 3
    assert body["columns"] == 2
    assert body["page_width"] == 1200
    assert body["page_height"] == 800
    assert body["source"] == {"x": 100.0, "y": 120.0, "width": 300.0, "height": 120.0}
    assert body["warnings"] == ["no_confidence"]
    # Every cell is unscored model output, and the blank source cell stays blank.
    assert body["cells"][0] == {
        "row": 0,
        "column": 0,
        "text": "Item",
        "confidence": None,
        "uncertain": False,
        "empty": False,
        "alignment": None,
        "rowspan": 1,
        "colspan": 1,
    }
    assert body["empty_cells"] == 1
    assert body["cells"][-1]["empty"] is True

    payload = stub_ai.state.last_payload
    assert payload is not None
    assert payload["model"] == "llava:7b"
    assert payload["messages"][-1]["images"]
    assert payload["format"] == "json"

    # Nothing is written to the element: the reply is only a proposal.
    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    )
    assert listed.json()[0]["text"] == ""

    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["task"] == "table_structure"
    assert usage["recent"][0]["page_id"] == page["id"]
    assert usage["by_task"] == [{"task": "table_structure", "used": 1}]


def test_ai_table_refuses_an_incomplete_grid(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    stub_ai.state.vision_content = json.dumps(
        {"rows": [["Item", "Qty"], ["Apples"]]}
    )
    page = upload_pages(client, project["id"], ["ai-table-ragged.png"])[0]
    element = _equation_region(client, project["id"], page["id"], kind="table")

    response = _table(client, project["id"], element["id"])
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "ai_table_ragged"

    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["outcome"] == "error"
    assert usage["recent"][0]["error_code"] == "ai_table_ragged"
    assert usage["recent"][0]["task"] == "table_structure"


def _insert_usage(
    *,
    model: str,
    task: str,
    outcome: str,
    created_at,
    project_id: str | None,
    error_code: str | None = None,
) -> None:
    import uuid

    from app.db.models import AiUsage
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        session.add(
            AiUsage(
                id=str(uuid.uuid4()),
                provider="ollama",
                model=model,
                task=task,
                outcome=outcome,
                error_code=error_code,
                project_id=project_id,
                page_id=None,
                block_id=None,
                created_at=created_at,
            )
        )
        session.commit()


def test_ai_usage_history_pages_filters_and_names_projects(
    client: TestClient, project: dict
) -> None:
    from datetime import datetime

    other = client.post(
        "/api/projects",
        json={"name": "Second Ledger Project", "description": ""},
    )
    assert other.status_code == 201, other.text
    other_id = other.json()["id"]

    # Oldest first in insertion order; the endpoint must return newest first.
    _insert_usage(
        model="cleanup-model",
        task="ocr_cleanup",
        outcome="success",
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        project_id=project["id"],
    )
    _insert_usage(
        model="cleanup-model",
        task="ocr_cleanup",
        outcome="error",
        error_code="ai_timeout",
        created_at=datetime(2026, 1, 1, 11, 0, 0),
        project_id=project["id"],
    )
    _insert_usage(
        model="vision-model",
        task="region_proposals",
        outcome="success",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        project_id=other_id,
    )
    _insert_usage(
        model="detached-model",
        task="equation_transcription",
        outcome="success",
        created_at=datetime(2026, 1, 1, 13, 0, 0),
        project_id=None,
    )

    response = client.get("/api/ai/usage/history")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 4
    assert body["limit"] == 25
    assert body["offset"] == 0
    assert [entry["model"] for entry in body["entries"]] == [
        "detached-model",
        "vision-model",
        "cleanup-model",
        "cleanup-model",
    ]
    assert body["entries"][0]["project_name"] is None
    assert body["entries"][1]["project_name"] == "Second Ledger Project"
    assert body["entries"][2]["project_name"] == "Quantum Mechanics"
    assert body["entries"][2]["outcome"] == "error"
    assert body["entries"][2]["error_code"] == "ai_timeout"

    page = client.get("/api/ai/usage/history", params={"limit": 2, "offset": 1})
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 4
    assert [entry["model"] for entry in page.json()["entries"]] == [
        "vision-model",
        "cleanup-model",
    ]

    failed = client.get("/api/ai/usage/history", params={"outcome": "error"})
    assert failed.status_code == 200, failed.text
    assert failed.json()["total"] == 1
    assert failed.json()["entries"][0]["error_code"] == "ai_timeout"

    regions = client.get(
        "/api/ai/usage/history", params={"task": "region_proposals"}
    )
    assert regions.status_code == 200, regions.text
    assert regions.json()["total"] == 1
    assert regions.json()["entries"][0]["project_name"] == "Second Ledger Project"

    combined = client.get(
        "/api/ai/usage/history",
        params={"task": "ocr_cleanup", "outcome": "success"},
    )
    assert combined.status_code == 200, combined.text
    assert combined.json()["total"] == 1
    assert combined.json()["entries"][0]["project_name"] == "Quantum Mechanics"

    assert client.get("/api/ai/usage/history", params={"limit": 0}).status_code == 422
    assert (
        client.get("/api/ai/usage/history", params={"task": "unknown"}).status_code
        == 422
    )


def test_cost_guard_classifies_the_effective_server() -> None:
    from types import SimpleNamespace

    from app.api.routes.ai import _effective_cost_class
    from app.schemas.settings import AiProfileSettings

    saved = SimpleNamespace(provider=None, base_url=None)
    paid = AiProfileSettings(
        provider="openai_compatible",
        base_url="http://192.0.2.10:1234/v1",
        model="remote-model",
        allow_remote=True,
        cost_class="paid",
    )
    free = paid.model_copy(update={"cost_class": "free"})
    # A stale local class next to a remote URL is never trusted.
    stale = paid.model_copy(update={"cost_class": "local"})
    loopback = AiProfileSettings(
        provider="openai_compatible",
        base_url="http://localhost:1234/v1",
        model="local-model",
        cost_class="paid",
        allow_remote=True,
    )

    assert _effective_cost_class(paid, saved) == "paid"
    assert _effective_cost_class(free, saved) == "free"
    assert _effective_cost_class(stale, saved) == "paid"
    # Loopback inference is local no matter what the saved class says.
    assert _effective_cost_class(loopback, saved) == "local"

    override = SimpleNamespace(
        provider=None, base_url="http://192.0.2.10:1234/v1"
    )
    assert _effective_cost_class(loopback, override) == "paid"
    empty_override = SimpleNamespace(provider="ollama", base_url="")
    assert _effective_cost_class(paid, empty_override) == "local"


def test_paid_profile_requires_explicit_confirmation(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    from app.services import ai as ai_service

    _configure_ai(client, base_url=stub_ai.base_url, vision_model="llava:7b")
    saved = client.patch(
        "/api/settings",
        json={
            "ai": {
                "text": {
                    "base_url": "http://192.0.2.10:11434",
                    "allow_remote": True,
                    "cost_class": "paid",
                },
                "vision": {
                    "base_url": "http://192.0.2.10:1234/v1",
                    "allow_remote": True,
                    "cost_class": "paid",
                },
            }
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ai"]["text"]["cost_class"] == "paid"

    def no_network(*_args, **_kwargs):
        raise AssertionError("A paid request must not reach the network.")

    monkeypatch.setattr(ai_service.urllib_request, "urlopen", no_network)

    page, run = _ocr_page(client, project, monkeypatch, "ai-paid-cleanup.png")
    cleanup = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert cleanup.status_code == 409, cleanup.text
    assert cleanup.json()["detail"]["code"] == "ai_paid_confirmation_required"

    vision = _vision(client, project["id"], page["id"])
    assert vision.status_code == 409, vision.text
    assert vision.json()["detail"]["code"] == "ai_paid_confirmation_required"

    element = _equation_region(client, project["id"], page["id"])
    equation = _equation(client, project["id"], element["id"])
    assert equation.status_code == 409, equation.text
    assert equation.json()["detail"]["code"] == "ai_paid_confirmation_required"

    # A refused request is never sent and never counts against the limit.
    assert _usage(client)["used"] == 0


def test_remote_free_profile_needs_no_confirmation(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    from urllib.error import URLError

    from app.services import ai as ai_service

    _configure_ai(client, base_url=stub_ai.base_url)
    saved = client.patch(
        "/api/settings",
        json={
            "ai": {
                "text": {
                    "base_url": "http://192.0.2.10:11434",
                    "allow_remote": True,
                    "cost_class": "free",
                }
            }
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ai"]["text"]["cost_class"] == "free"

    def unreachable(*_args, **_kwargs):
        raise URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(ai_service.urllib_request, "urlopen", unreachable)

    page, run = _ocr_page(client, project, monkeypatch, "ai-free-cleanup.png")
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    # The request was allowed through; only the server itself was unreachable.
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "ai_unreachable"
    assert _usage(client)["used"] == 1


def test_local_profile_accepts_confirm_paid_flag(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    page, run = _ocr_page(client, project, monkeypatch, "ai-local-confirmed.png")
    response = _suggest(
        client,
        project["id"],
        page["id"],
        run["blocks"][0]["id"],
        {"confirm_paid": True},
    )
    assert response.status_code == 201, response.text
    assert ("POST", "/api/chat") in stub_ai.state.requests


def test_remote_profile_cannot_stay_marked_local(client: TestClient) -> None:
    saved = client.patch(
        "/api/settings",
        json={
            "ai": {
                "text": {
                    "provider": "openai_compatible",
                    "base_url": "http://192.0.2.10:1234",
                    "allow_remote": True,
                    "cost_class": "local",
                }
            }
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ai"]["text"]["cost_class"] == "paid"


def test_legacy_remote_profile_without_a_cost_class_is_paid(
    client: TestClient,
) -> None:
    from app.db.models import AppSetting
    from app.db.session import get_session_factory

    session = get_session_factory()()
    try:
        session.add(
            AppSetting(
                key="app",
                value={
                    "ai": {
                        "text": {
                            "provider": "openai_compatible",
                            "base_url": "http://192.0.2.10:1234/v1",
                            "model": "remote-model",
                            "allow_remote": True,
                        }
                    }
                },
            )
        )
        session.commit()
    finally:
        session.close()

    ai_settings = client.get("/api/settings").json()["ai"]
    assert ai_settings["text"]["cost_class"] == "paid"
    # Vision was never saved remotely, so it keeps the local default.
    assert ai_settings["vision"]["cost_class"] == "local"


def test_probe_reports_rate_limit_and_retry_after(
    client: TestClient, stub_ai
) -> None:
    stub_ai.state.fail_status = 429
    stub_ai.state.retry_after = "30"

    response = client.post(
        "/api/ai/probe",
        json={"provider": "ollama", "base_url": stub_ai.base_url},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "http_error"
    assert body["error_code"] == "ai_rate_limited"
    assert body["http_status"] == 429
    assert body["retry_after_seconds"] == 30


def test_probe_reports_auth_failure_without_a_retry_hint(
    client: TestClient, stub_ai
) -> None:
    stub_ai.state.fail_status = 401

    body = client.post(
        "/api/ai/probe",
        json={"provider": "openai_compatible", "base_url": stub_ai.base_url_v1},
    ).json()
    assert body["status"] == "http_error"
    assert body["error_code"] == "ai_auth_failed"
    assert body["http_status"] == 401
    assert body["retry_after_seconds"] is None


def test_cleanup_surfaces_a_rate_limit_without_retrying(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configure_ai(client, base_url=stub_ai.base_url)
    stub_ai.state.fail_status = 429
    stub_ai.state.retry_after = "12"

    page, run = _ocr_page(client, project, monkeypatch, "ai-rate-limited.png")
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "ai_rate_limited"
    # Exactly one provider call: nothing is retried or switched silently.
    assert stub_ai.state.requests.count(("POST", "/api/chat")) == 1
    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["outcome"] == "error"
    assert usage["recent"][0]["error_code"] == "ai_rate_limited"


def test_retry_after_parser_is_defensive() -> None:
    from app.services.ai import MAX_RETRY_AFTER_SECONDS, _retry_after_seconds

    assert _retry_after_seconds({"Retry-After": "45"}) == 45
    assert _retry_after_seconds({"Retry-After": "  7 "}) == 7
    assert (
        _retry_after_seconds({"Retry-After": "999999999"})
        == MAX_RETRY_AFTER_SECONDS
    )
    assert _retry_after_seconds({"Retry-After": "-5"}) is None
    assert _retry_after_seconds({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}) is None
    assert _retry_after_seconds(None) is None
    assert _retry_after_seconds({}) is None
