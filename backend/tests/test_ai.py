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
        self.last_payload: dict | None = None


def _stub_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    raw = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
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
            state.last_payload = payload
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
        ai["vision_model"] = vision_model
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
    }

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
    }

    limited = client.patch("/api/settings", json={"ai": {"request_limit": 25}})
    assert limited.status_code == 200, limited.text
    assert limited.json()["ai"]["request_limit"] == 25
    assert client.get("/api/ai/usage").json()["request_limit"] == 25

    for bad in (
        {"base_url": "ftp://127.0.0.1:1234"},
        {"base_url": "http://user:secret@127.0.0.1:1234"},
        {"model": "x" * 201},
    ):
        response = client.patch("/api/settings", json={"ai": {"text": bad}})
        assert response.status_code == 422, bad

    for bad_limit in (-1, 10_001):
        response = client.patch("/api/settings", json={"ai": {"request_limit": bad_limit}})
        assert response.status_code == 422, bad_limit


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
    assert empty["request_limit"] == 0
    assert empty["remaining"] is None

    created = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert created.status_code == 201, created.text
    after_success = _usage(client)
    assert after_success["used"] == 1
    assert after_success["successful"] == 1
    assert after_success["failed"] == 0
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
