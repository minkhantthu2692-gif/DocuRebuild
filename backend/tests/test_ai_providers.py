"""Adapter and security tests for the provider layer (no database involved)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services import ai_providers


class _State:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict | None]] = []
        self.auth: list[str | None] = []


@pytest.fixture()
def provider_server():
    state = _State()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            return

        def _send(self, status: int, payload, headers: dict | None = None) -> None:
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            state.requests.append(("GET", self.path, None))
            state.auth.append(self.headers.get("x-goog-api-key") or self.headers.get("x-api-key") or self.headers.get("Authorization"))
            if self.path.startswith("/redirect"):
                self._send(302, {}, {"Location": "/v1/models"})
            elif self.path == "/v1/models":
                self._send(
                    200,
                    {
                        "data": [
                            {
                                "id": "vision-model",
                                "name": "Vision Model",
                                "architecture": {
                                    "input_modalities": ["text", "image"],
                                    "output_modalities": ["text"],
                                },
                                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                                "context_length": 32000,
                            }
                        ]
                    },
                )
            elif self.path == "/api/tags":
                self._send(
                    200,
                    {
                        "models": [
                            {
                                "name": "qwen2.5:7b",
                                "model": "qwen2.5:7b",
                                "details": {"family": "qwen2", "parameter_size": "7B"},
                            }
                        ]
                    },
                )
            elif self.path == "/api/version":
                self._send(200, {"version": "0.5.1"})
            elif self.path == "/v1beta/models?pageSize=1000":
                self._send(
                    200,
                    {
                        "models": [
                            {
                                "name": "models/gemini-pro",
                                "displayName": "Gemini Pro",
                                "inputTokenLimit": 30000,
                                "supportedGenerationMethods": ["generateContent"],
                            },
                            {
                                "name": "models/embedding",
                                "supportedGenerationMethods": ["embedContent"],
                            },
                        ]
                    },
                )
            elif self.path == "/v1/models?limit=1000":
                self._send(
                    200,
                    {
                        "data": [
                            {
                                "id": "claude-sonnet",
                                "display_name": "Claude Sonnet",
                                "type": "model",
                            }
                        ]
                    },
                )
            elif self.path == "/huge":
                self._send(200, b"{" + b" " * (ai_providers.MAX_RESPONSE_BYTES + 10) + b"}")
            elif self.path == "/limited":
                self._send(429, {"error": "slow down"}, {"Retry-After": "45"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            state.requests.append(("POST", self.path, body))
            state.auth.append(self.headers.get("x-goog-api-key") or self.headers.get("x-api-key") or self.headers.get("Authorization"))
            if self.path == "/v1/chat/completions":
                self._send(
                    200,
                    {
                        "choices": [{"message": {"role": "assistant", "content": "openai text"}}],
                        "usage": {
                            "prompt_tokens": 11,
                            "completion_tokens": 7,
                            "total_tokens": 18,
                        },
                    },
                )
            elif self.path == "/api/chat":
                self._send(
                    200,
                    {
                        "message": {"role": "assistant", "content": "ollama text"},
                        "prompt_eval_count": 5,
                        "eval_count": 9,
                    },
                )
            elif self.path == "/v1/messages":
                self._send(
                    200,
                    {
                        "content": [
                            {"type": "text", "text": "anthropic "},
                            {"type": "tool_use", "id": "x"},
                            {"type": "text", "text": "text"},
                        ],
                        "usage": {"input_tokens": 3, "output_tokens": 4},
                    },
                )
            elif self.path == "/v1beta/models/gemini-pro:generateContent":
                self._send(
                    200,
                    {
                        "candidates": [
                            {"content": {"parts": [{"text": "gemini text"}]}}
                        ],
                        "usageMetadata": {
                            "promptTokenCount": 6,
                            "candidatesTokenCount": 8,
                            "totalTokenCount": 14,
                        },
                    },
                )
            else:
                self._send(404, {"error": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    yield base, state
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_registry_has_providers_but_no_model_catalog() -> None:
    catalog = {item["id"]: item for item in ai_providers.provider_catalog()}
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
        assert provider in catalog
    assert all("models" not in item for item in catalog.values())
    assert catalog["ollama"]["requires_api_key"] is False
    assert catalog["openai"]["requires_api_key"] is True


def test_openai_adapter_sends_text_and_vision(provider_server) -> None:
    base, state = provider_server
    reply = ai_providers.complete(
        "openai_compatible",
        base_url=f"{base}/v1",
        model="vision-model",
        system_prompt="system",
        user_text="describe",
        api_key="sk-test",
    )
    assert reply.text == "openai text"
    assert (reply.input_tokens, reply.output_tokens, reply.total_tokens) == (11, 7, 18)
    method, path, payload = state.requests[-1]
    assert (method, path) == ("POST", "/v1/chat/completions")
    assert payload["model"] == "vision-model"
    assert payload["messages"][0] == {"role": "system", "content": "system"}
    assert state.auth[-1] == "Bearer sk-test"

    ai_providers.complete(
        "openai_compatible",
        base_url=f"{base}/v1",
        model="vision-model",
        system_prompt="system",
        user_text="describe",
        api_key=None,
        image_b64="abc123",
        json_mode=True,
    )
    content = state.requests[-1][2]["messages"][-1]["content"]
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,abc123"
    # OpenAI-compatible servers do not share a JSON flag, so none is sent.
    assert "response_format" not in state.requests[-1][2]


def test_ollama_adapter_uses_native_chat(provider_server) -> None:
    base, state = provider_server
    reply = ai_providers.complete(
        "ollama",
        base_url=base,
        model="qwen2.5:7b",
        system_prompt="system",
        user_text="hello",
        api_key=None,
        image_b64="abc",
        json_mode=True,
    )
    assert reply.text == "ollama text"
    assert (reply.input_tokens, reply.output_tokens) == (5, 9)
    method, path, payload = state.requests[-1]
    assert (method, path) == ("POST", "/api/chat")
    assert payload["format"] == "json"
    assert payload["stream"] is False
    assert payload["messages"][-1]["images"] == ["abc"]


def test_anthropic_adapter_uses_messages_and_api_key_header(provider_server) -> None:
    base, state = provider_server
    reply = ai_providers.complete(
        "anthropic",
        base_url=f"{base}/v1",
        model="claude-sonnet",
        system_prompt="system",
        user_text="hello",
        api_key="sk-ant",
        image_b64="abc",
    )
    assert reply.text == "anthropic text"
    assert (reply.input_tokens, reply.output_tokens) == (3, 4)
    method, path, payload = state.requests[-1]
    assert (method, path) == ("POST", "/v1/messages")
    assert payload["system"] == "system"
    assert payload["messages"][0]["content"][0]["type"] == "image"
    assert payload["messages"][0]["content"][1]["text"] == "hello"
    assert state.auth[-1] == "sk-ant"


def test_gemini_adapter_uses_generate_content(provider_server) -> None:
    base, state = provider_server
    reply = ai_providers.complete(
        "gemini",
        base_url=f"{base}/v1beta",
        model="models/gemini-pro",
        system_prompt="system",
        user_text="hello",
        api_key="gm-key",
        image_b64="abc",
        json_mode=True,
    )
    assert reply.text == "gemini text"
    assert (reply.input_tokens, reply.output_tokens, reply.total_tokens) == (6, 8, 14)
    method, path, payload = state.requests[-1]
    assert (method, path) == ("POST", "/v1beta/models/gemini-pro:generateContent")
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["contents"][0]["parts"][1]["inlineData"]["data"] == "abc"
    assert state.auth[-1] == "gm-key"


def test_discovery_parses_each_catalog(provider_server) -> None:
    base, _state = provider_server
    openai = ai_providers.discover_models(
        ai_providers.get_provider("openai_compatible"),
        f"{base}/v1",
        api_key=None,
    )
    entry = openai.models[0]
    assert entry["model_id"] == "vision-model"
    assert entry["input_modalities"] == ["image", "text"]
    assert entry["pricing"]["prompt"] == 0.000001

    ollama = ai_providers.discover_models(
        ai_providers.get_provider("ollama"), base, api_key=None
    )
    assert ollama.version == "0.5.1"
    assert ollama.models[0]["model_id"] == "qwen2.5:7b"
    assert ollama.models[0]["model_metadata"]["parameter_size"] == "7B"

    anthropic = ai_providers.discover_models(
        ai_providers.get_provider("anthropic"), f"{base}/v1", api_key="k"
    )
    assert anthropic.models[0]["display_name"] == "Claude Sonnet"

    gemini = ai_providers.discover_models(
        ai_providers.get_provider("gemini"), f"{base}/v1beta", api_key="k"
    )
    # Models that cannot generate content are not offered for tasks.
    assert [item["model_id"] for item in gemini.models] == ["gemini-pro"]
    assert gemini.models[0]["context_window"] == 30000


def test_redirects_are_not_followed(provider_server) -> None:
    base, state = provider_server
    with pytest.raises(ai_providers.ProviderError) as excinfo:
        ai_providers.discover_models(
            ai_providers.get_provider("openai_compatible"),
            f"{base}/redirect",
            api_key=None,
        )
    assert excinfo.value.code == "ai_http_error"
    # The target was never requested.
    assert all(path != "/v1/models" for _method, path, _payload in state.requests)


def test_oversized_and_rate_limited_responses_are_reported(provider_server) -> None:
    base, _state = provider_server

    with pytest.raises(ai_providers.ProviderError) as huge:
        ai_providers._request_json(f"{base}/huge", headers={}, timeout=5.0)
    assert huge.value.code == "ai_invalid_response"

    with pytest.raises(ai_providers.ProviderError) as limited:
        ai_providers._request_json(f"{base}/limited", headers={}, timeout=5.0)
    assert limited.value.code == "ai_rate_limited"
    assert limited.value.retry_after_seconds == 45
    assert limited.value.http_status == 429


def test_url_validation_rejects_unsafe_endpoints() -> None:
    cases = [
        ("https://169.254.169.254/v1", True, "ai_url_not_allowed"),
        ("https://metadata.google.internal/v1", True, "ai_url_not_allowed"),
        ("https://user:secret@example.com/v1", True, "ai_url_not_allowed"),
        ("http://example.com/v1", False, "ai_remote_not_allowed"),
        ("http://example.com/v1", True, "ai_https_required"),
        ("ftp://127.0.0.1:1234", False, "ai_invalid_url"),
    ]
    for url, allow_remote, code in cases:
        with pytest.raises(ai_providers.ProviderError) as excinfo:
            ai_providers.normalize_base_url(
                "openai_compatible", url, allow_remote=allow_remote
            )
        assert excinfo.value.code == code, url


def test_loopback_urls_are_local_and_defaults_are_applied() -> None:
    for host in ("127.0.0.1", "localhost", "app.localhost", "[::1]"):
        assert ai_providers.is_loopback_url(f"http://{host}:11434")
    assert not ai_providers.is_loopback_url("https://api.openai.com/v1")
    assert ai_providers.normalize_base_url("openai", "", allow_remote=True) == (
        "https://api.openai.com/v1"
    )
    assert ai_providers.normalize_base_url("ollama", "") == "http://127.0.0.1:11434"
    with pytest.raises(ai_providers.ProviderError) as required:
        ai_providers.normalize_base_url("openai_compatible", "")
    assert required.value.code == "ai_base_url_required"
    # Remote defaults still need consent before any document text can leave.
    with pytest.raises(ai_providers.ProviderError) as consent:
        ai_providers.normalize_base_url("openai", "")
    assert consent.value.code == "ai_remote_not_allowed"


def test_retry_after_parser_is_defensive() -> None:
    class Headers(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    assert ai_providers._retry_after_seconds(Headers({"Retry-After": "45"})) == 45
    assert ai_providers._retry_after_seconds(Headers({"Retry-After": " 7 "})) == 7
    assert (
        ai_providers._retry_after_seconds(Headers({"Retry-After": "999999999"}))
        == ai_providers.MAX_RETRY_AFTER_SECONDS
    )
    assert ai_providers._retry_after_seconds(Headers({"Retry-After": "-5"})) is None
    assert ai_providers._retry_after_seconds(Headers({})) is None
    assert ai_providers._retry_after_seconds(None) is None


def test_invalid_response_shapes_raise_provider_errors(provider_server) -> None:
    base, _state = provider_server
    # The /v1/models stub is valid, so an unknown path must surface a clear code.
    with pytest.raises(ai_providers.ProviderError) as excinfo:
        ai_providers.discover_models(
            ai_providers.get_provider("openai_compatible"),
            f"{base}/missing",
            api_key=None,
        )
    assert excinfo.value.code == "ai_endpoint_not_found"
    assert excinfo.value.http_status == 404

