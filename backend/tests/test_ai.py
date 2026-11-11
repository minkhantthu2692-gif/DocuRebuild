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
        self.invalid_tags = False
        self.requests: list[tuple[str, str]] = []


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
            assert payload["messages"][0]["role"] == "system"
            if self.path == "/api/chat":
                _stub_response(
                    self,
                    200,
                    {"message": {"role": "assistant", "content": state.ollama_content}},
                )
            elif self.path == "/v1/chat/completions":
                _stub_response(
                    self,
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": state.openai_content,
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
) -> None:
    response = client.patch(
        "/api/settings",
        json={"ai": {"text": {"provider": provider, "base_url": base_url, "model": model}}},
    )
    assert response.status_code == 200, response.text


def _suggest(
    client: TestClient, project_id: str, page_id: str, block_id: str, payload: dict | None = None
):
    return client.post(
        f"/api/projects/{project_id}/pages/{page_id}/ocr/blocks/{block_id}/ai-suggestions",
        json=payload or {},
    )


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


def test_ai_profile_settings_validation_and_persistence(client: TestClient) -> None:
    defaults = client.get("/api/settings").json()["ai"]["text"]
    assert defaults == {"provider": "ollama", "base_url": "", "model": ""}

    saved = client.patch(
        "/api/settings",
        json={"ai": {"text": {"provider": "openai_compatible", "model": " local-model "}}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ai"]["text"] == {
        "provider": "openai_compatible",
        "base_url": "",
        "model": "local-model",
    }

    for bad in (
        {"base_url": "ftp://127.0.0.1:1234"},
        {"base_url": "http://user:secret@127.0.0.1:1234"},
        {"model": "x" * 201},
    ):
        response = client.patch("/api/settings", json={"ai": {"text": bad}})
        assert response.status_code == 422, bad


def test_cleanup_requires_a_configured_model(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _ocr_page(client, project, monkeypatch, "ai-unconfigured.png")
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ai_not_configured"


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
