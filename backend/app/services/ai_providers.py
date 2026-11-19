"""Provider registry and adapters for the unified BYOK AI layer.

The registry contains provider *definitions* (endpoint defaults, auth style and
supported operations), never a catalog of model IDs. Models are always fetched
from the provider with the user's credential, or added manually only for a
provider that genuinely has no discovery endpoint.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 1_000_000
PROBE_TIMEOUT = 8.0
DEFAULT_TIMEOUT = 60.0
MAX_RETRY_AFTER_SECONDS = 86_400
USER_AGENT = "DocuRebuild/0.1"
METADATA_HOSTS = frozenset({"169.254.169.254", "metadata.google.internal"})
OPENAI_CHAT_SUFFIX = "/chat/completions"

ProviderKind = Literal["openai", "anthropic", "gemini", "ollama"]


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    kind: ProviderKind
    default_base_url: str
    # A custom server has no safe default; the user must supply its URL.
    requires_base_url: bool = False
    # True when the provider has no documented model listing endpoint.
    supports_model_discovery: bool = True
    # Manual model entry is only offered when discovery is unavailable, and is
    # always marked as manually entered in the model registry.
    allows_manual_models: bool = False
    local_default: bool = False
    # Optional for loopback and self-hosted OpenAI-compatible servers.
    requires_api_key: bool = True
    docs_url: str | None = None


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="ollama",
        name="Ollama (local)",
        kind="ollama",
        default_base_url="http://127.0.0.1:11434",
        local_default=True,
        requires_api_key=False,
        docs_url="https://ollama.com",
    ),
    ProviderSpec(
        id="openai_compatible",
        name="Custom OpenAI-compatible",
        kind="openai",
        default_base_url="",
        requires_base_url=True,
        allows_manual_models=True,
        requires_api_key=False,
    ),
    ProviderSpec(
        id="openai",
        name="OpenAI",
        kind="openai",
        default_base_url="https://api.openai.com/v1",
        docs_url="https://platform.openai.com/docs",
    ),
    ProviderSpec(
        id="anthropic",
        name="Anthropic",
        kind="anthropic",
        default_base_url="https://api.anthropic.com/v1",
        docs_url="https://docs.anthropic.com",
    ),
    ProviderSpec(
        id="gemini",
        name="Google Gemini",
        kind="gemini",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        docs_url="https://ai.google.dev/gemini-api/docs",
    ),
    ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        kind="openai",
        default_base_url="https://openrouter.ai/api/v1",
        docs_url="https://openrouter.ai/docs",
    ),
    ProviderSpec(
        id="groq",
        name="Groq",
        kind="openai",
        default_base_url="https://api.groq.com/openai/v1",
        docs_url="https://console.groq.com/docs",
    ),
    ProviderSpec(
        id="mistral",
        name="Mistral AI",
        kind="openai",
        default_base_url="https://api.mistral.ai/v1",
        docs_url="https://docs.mistral.ai",
    ),
    ProviderSpec(
        id="deepseek",
        name="DeepSeek",
        kind="openai",
        default_base_url="https://api.deepseek.com/v1",
        docs_url="https://api-docs.deepseek.com",
    ),
    ProviderSpec(
        id="xai",
        name="xAI",
        kind="openai",
        default_base_url="https://api.x.ai/v1",
        docs_url="https://docs.x.ai",
    ),
    ProviderSpec(
        id="together",
        name="Together AI",
        kind="openai",
        default_base_url="https://api.together.xyz/v1",
        docs_url="https://docs.together.ai",
    ),
    ProviderSpec(
        id="fireworks",
        name="Fireworks AI",
        kind="openai",
        default_base_url="https://api.fireworks.ai/inference/v1",
        docs_url="https://docs.fireworks.ai",
    ),
    ProviderSpec(
        id="cerebras",
        name="Cerebras",
        kind="openai",
        default_base_url="https://api.cerebras.ai/v1",
        docs_url="https://inference-docs.cerebras.ai",
    ),
    ProviderSpec(
        id="perplexity",
        name="Perplexity",
        kind="openai",
        default_base_url="https://api.perplexity.ai",
        # Perplexity documents chat completions but not a model listing API.
        supports_model_discovery=False,
        allows_manual_models=True,
        docs_url="https://docs.perplexity.ai",
    ),
)

PROVIDER_BY_ID = {spec.id: spec for spec in PROVIDERS}


class ProviderError(Exception):
    """A safe, normalized provider failure.

    Messages deliberately contain no provider response body, URL query or key.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
        category: str = "provider",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.category = category

    @property
    def retryable_with_another_key(self) -> bool:
        """Only failures that happened before generation may try another key."""
        return self.category in {"auth", "rate_limit"}


@dataclass
class ProviderReply:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class DiscoveryResult:
    models: list[dict[str, Any]] = field(default_factory=list)
    version: str | None = None


def provider_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "kind": spec.kind,
            "default_base_url": spec.default_base_url,
            "requires_base_url": spec.requires_base_url,
            "supports_model_discovery": spec.supports_model_discovery,
            "allows_manual_models": spec.allows_manual_models,
            "local_default": spec.local_default,
            "requires_api_key": spec.requires_api_key,
            "docs_url": spec.docs_url,
        }
        for spec in PROVIDERS
    ]


def get_provider(provider_id: str) -> ProviderSpec:
    spec = PROVIDER_BY_ID.get(provider_id)
    if spec is None:
        raise ProviderError("ai_unknown_provider", "Unknown AI provider.", category="config")
    return spec


def _is_loopback(hostname: str | None) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_private_hostname(hostname: str | None) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host.endswith((".local", ".lan", ".internal", ".home")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_link_local


def is_loopback_url(value: str) -> bool:
    try:
        return _is_loopback(urllib_parse.urlparse((value or "").strip()).hostname)
    except ValueError:
        return False


def _reject_unsafe_host(hostname: str | None) -> None:
    host = (hostname or "").strip().lower()
    if not host:
        raise ProviderError("ai_invalid_url", "The provider URL is not valid.", category="config")
    if host in METADATA_HOSTS:
        raise ProviderError(
            "ai_url_not_allowed",
            "That provider address is not allowed.",
            category="config",
        )
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_link_local or address.is_multicast or address.is_reserved:
        raise ProviderError(
            "ai_url_not_allowed",
            "That provider address is not allowed.",
            category="config",
        )


def normalize_base_url(
    provider_id: str,
    value: str,
    *,
    allow_remote: bool = False,
) -> str:
    spec = get_provider(provider_id)
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        if spec.requires_base_url:
            raise ProviderError(
                "ai_base_url_required",
                "Enter the base URL of your OpenAI-compatible server.",
                category="config",
            )
        cleaned = spec.default_base_url.rstrip("/")
    parsed = urllib_parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderError("ai_invalid_url", "The provider URL is not valid.", category="config")
    if parsed.username or parsed.password:
        raise ProviderError(
            "ai_url_not_allowed",
            "The provider URL must not contain credentials.",
            category="config",
        )
    _reject_unsafe_host(parsed.hostname)
    loopback = _is_loopback(parsed.hostname)
    private = _is_private_hostname(parsed.hostname)
    if not loopback and not allow_remote:
        raise ProviderError(
            "ai_remote_not_allowed",
            "This provider is not on loopback. Enable remote consent for this connection first.",
            category="config",
        )
    if not loopback and not private and parsed.scheme != "https":
        raise ProviderError(
            "ai_https_required",
            "Remote provider endpoints must use HTTPS.",
            category="config",
        )
    # OpenAI-style APIs are addressed under /v1. A base URL with a meaningful
    # path is kept exactly as entered (for gateways and self-hosted proxies).
    if spec.kind == "openai" and (not parsed.path or parsed.path == "/"):
        cleaned = f"{cleaned}/v1"
    return cleaned


def _error_for_http(status: int, headers: Any) -> ProviderError:
    retry_after = _retry_after_seconds(headers)
    if status == 429:
        return ProviderError(
            "ai_rate_limited",
            "The provider is rate limiting requests.",
            http_status=status,
            retry_after_seconds=retry_after,
            category="rate_limit",
        )
    if status == 401:
        return ProviderError(
            "ai_auth_failed",
            "The provider rejected this API key.",
            http_status=status,
            category="auth",
        )
    if status == 403:
        return ProviderError(
            "ai_permission_denied",
            "This API key is not allowed to use that endpoint or model.",
            http_status=status,
            category="auth",
        )
    if status == 404:
        return ProviderError(
            "ai_endpoint_not_found",
            "The provider endpoint was not found. Check the base URL.",
            http_status=status,
        )
    if status >= 500:
        return ProviderError(
            "ai_provider_unavailable",
            "The provider is temporarily unavailable.",
            http_status=status,
            category="server",
        )
    return ProviderError(
        "ai_http_error",
        "The provider rejected the request.",
        http_status=status,
    )


def _retry_after_seconds(headers: Any) -> int | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return min(seconds, MAX_RETRY_AFTER_SECONDS)


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    """Never follow a redirect; a changed destination is treated as an error."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_OPENER = urllib_request.build_opener(_NoRedirect)


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> tuple[int, Any]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        **headers,
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib_request.Request(
        url,
        data=data,
        headers=request_headers,
        method="POST" if data is not None else "GET",
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ProviderError(
                    "ai_invalid_response",
                    "The provider returned more data than this app accepts.",
                )
            if not raw:
                return response.status, {}
            try:
                return response.status, json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ProviderError(
                    "ai_invalid_response",
                    "The provider returned an unexpected response.",
                ) from exc
    except urllib_error.HTTPError as exc:
        raise _error_for_http(exc.code, exc.headers) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderError(
            "ai_timeout", "The provider did not answer in time.", category="network"
        ) from exc
    except urllib_error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ProviderError(
                "ai_timeout", "The provider did not answer in time.", category="network"
            ) from exc
        raise ProviderError(
            "ai_unreachable", "The provider could not be reached.", category="network"
        ) from exc
    except (OSError, ValueError) as exc:
        raise ProviderError(
            "ai_unreachable", "The provider could not be reached.", category="network"
        ) from exc


def _auth_headers(spec: ProviderSpec, api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    if spec.kind == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    if spec.kind == "gemini":
        return {"x-goog-api-key": api_key}
    return {"Authorization": f"Bearer {api_key}"}


def _normalize_pricing(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, Any] = {}
    for key in ("prompt", "completion", "request", "image", "prompt_tokens", "completion_tokens"):
        raw = value.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            if float(raw) >= 0:
                normalized[key] = float(raw)
        elif isinstance(raw, str):
            try:
                number = float(raw)
            except ValueError:
                continue
            if number >= 0:
                normalized[key] = number
    return normalized or None


def _modalities(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned = sorted(
        {
            str(item).strip().lower()
            for item in value
            if isinstance(item, str) and str(item).strip()
        }
    )
    return cleaned or None


def _openai_model_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    model_id = item.get("id")
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    architecture = item.get("architecture")
    architecture = architecture if isinstance(architecture, dict) else {}
    input_modalities = _modalities(architecture.get("input_modalities"))
    output_modalities = _modalities(architecture.get("output_modalities"))
    supported_parameters = item.get("supported_parameters")
    supports_tools = None
    supports_streaming = None
    if isinstance(supported_parameters, list):
        names = {str(value).lower() for value in supported_parameters if isinstance(value, str)}
        supports_tools = bool({"tools", "tool_choice"} & names)
        supports_streaming = "stream" in names
    context_window = item.get("context_length") or item.get("context_window")
    if not isinstance(context_window, int) or isinstance(context_window, bool) or context_window <= 0:
        context_window = None
    display_name = item.get("name")
    family = item.get("owned_by")
    return {
        "model_id": model_id.strip(),
        "display_name": display_name.strip() if isinstance(display_name, str) and display_name.strip() else None,
        "family": family.strip() if isinstance(family, str) and family.strip() else None,
        "context_window": context_window,
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_tools": supports_tools,
        "supports_streaming": supports_streaming,
        "pricing": _normalize_pricing(item.get("pricing")),
        "model_metadata": {
            key: item[key]
            for key in ("owned_by", "created", "description")
            if key in item and isinstance(item[key], (str, int, float))
        }
        or None,
        "source": "discovered",
    }


def discover_models(
    spec: ProviderSpec,
    base_url: str,
    *,
    api_key: str | None,
    timeout: float = PROBE_TIMEOUT,
) -> DiscoveryResult:
    """Fetch a provider's model list; never downloads or generates anything."""
    if not spec.supports_model_discovery:
        raise ProviderError(
            "ai_model_discovery_unsupported",
            "This provider does not offer a model listing endpoint. Add a model ID manually.",
            category="config",
        )
    headers = _auth_headers(spec, api_key)
    version: str | None = None
    if spec.kind == "ollama":
        _status, body = _request_json(f"{base_url}/api/tags", headers=headers, timeout=timeout)
        if not isinstance(body, dict) or not isinstance(body.get("models"), list):
            raise ProviderError(
                "ai_invalid_response", "The provider returned an unexpected model list."
            )
        models: list[dict[str, Any]] = []
        for item in body["models"]:
            if not isinstance(item, dict):
                continue
            model_id = item.get("model") or item.get("name")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            family = details.get("family")
            models.append(
                {
                    "model_id": model_id.strip(),
                    "display_name": None,
                    "family": family if isinstance(family, str) else None,
                    "context_window": None,
                    "input_modalities": None,
                    "output_modalities": None,
                    "supports_tools": None,
                    "supports_streaming": None,
                    "pricing": None,
                    "model_metadata": {
                        key: details[key]
                        for key in ("parameter_size", "quantization_level")
                        if key in details and isinstance(details[key], str)
                    }
                    or None,
                    "source": "discovered",
                }
            )
        models.sort(key=lambda entry: entry["model_id"].lower())
        try:
            _version_status, version_body = _request_json(
                f"{base_url}/api/version", headers=headers, timeout=timeout
            )
            if isinstance(version_body, dict) and isinstance(version_body.get("version"), str):
                version = version_body["version"]
        except ProviderError:
            version = None
        return DiscoveryResult(models, version)

    if spec.kind == "anthropic":
        url = f"{base_url}/models?limit=1000"
        _status, body = _request_json(url, headers=headers, timeout=timeout)
        raw = body.get("data") if isinstance(body, dict) else None
        if not isinstance(raw, list):
            raise ProviderError(
                "ai_invalid_response", "The provider returned an unexpected model list."
            )
        models = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            display_name = item.get("display_name")
            models.append(
                {
                    "model_id": model_id.strip(),
                    "display_name": display_name.strip()
                    if isinstance(display_name, str) and display_name.strip()
                    else None,
                    "family": None,
                    "context_window": None,
                    "input_modalities": None,
                    "output_modalities": None,
                    "supports_tools": None,
                    "supports_streaming": None,
                    "pricing": None,
                    "model_metadata": {
                        key: item[key]
                        for key in ("created_at", "type")
                        if key in item and isinstance(item[key], str)
                    }
                    or None,
                    "source": "discovered",
                }
            )
        models.sort(key=lambda entry: entry["model_id"].lower())
        return DiscoveryResult(models, None)

    if spec.kind == "gemini":
        url = f"{base_url}/models?pageSize=1000"
        _status, body = _request_json(url, headers=headers, timeout=timeout)
        raw = body.get("models") if isinstance(body, dict) else None
        if not isinstance(raw, list):
            raise ProviderError(
                "ai_invalid_response", "The provider returned an unexpected model list."
            )
        models = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            model_id = name.strip()
            if model_id.startswith("models/"):
                model_id = model_id[len("models/") :]
            methods = item.get("supportedGenerationMethods")
            if isinstance(methods, list) and "generateContent" not in methods:
                continue
            input_limit = item.get("inputTokenLimit")
            context_window = (
                input_limit
                if isinstance(input_limit, int) and not isinstance(input_limit, bool) and input_limit > 0
                else None
            )
            display_name = item.get("displayName")
            models.append(
                {
                    "model_id": model_id,
                    "display_name": display_name.strip()
                    if isinstance(display_name, str) and display_name.strip()
                    else None,
                    "family": None,
                    "context_window": context_window,
                    "input_modalities": None,
                    "output_modalities": None,
                    "supports_tools": None,
                    "supports_streaming": None,
                    "pricing": None,
                    "model_metadata": {
                        key: item[key]
                        for key in ("description", "outputTokenLimit")
                        if key in item and isinstance(item[key], (str, int))
                    }
                    or None,
                    "source": "discovered",
                }
            )
        models.sort(key=lambda entry: entry["model_id"].lower())
        return DiscoveryResult(models, None)

    # OpenAI-compatible: /models is the contract shared by the providers above.
    _status, body = _request_json(f"{base_url}/models", headers=headers, timeout=timeout)
    raw = body.get("data") if isinstance(body, dict) else None
    if raw is None and isinstance(body, dict):
        raw = body.get("models")
    if not isinstance(raw, list):
        raise ProviderError(
            "ai_invalid_response", "The provider returned an unexpected model list."
        )
    models = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry = _openai_model_entry(item)
        if entry is not None:
            models.append(entry)
    models.sort(key=lambda entry: entry["model_id"].lower())
    return DiscoveryResult(models, None)


def _content_text(content: Any, provider: str) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    raise ProviderError(
        "ai_invalid_response", "The provider returned an unexpected response."
    )


def _usage_from_openai(body: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return None, None, None
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    total_tokens = usage.get("total_tokens")
    return (
        input_tokens if isinstance(input_tokens, int) and not isinstance(input_tokens, bool) else None,
        output_tokens if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) else None,
        total_tokens if isinstance(total_tokens, int) and not isinstance(total_tokens, bool) else None,
    )


def _ollama_chat(
    base_url: str,
    model: str,
    system_prompt: str,
    user_text: str,
    image_b64: str | None,
    api_key: str | None,
    temperature: float,
    timeout: float,
    json_mode: bool,
) -> ProviderReply:
    message: dict[str, Any] = {"role": "user", "content": user_text}
    if image_b64:
        message["images"] = [image_b64]
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            message,
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }
    if json_mode:
        payload["format"] = "json"
    _status, body = _request_json(
        f"{base_url}/api/chat",
        headers=_auth_headers(get_provider("ollama"), api_key),
        payload=payload,
        timeout=timeout,
    )
    if not isinstance(body, dict) or not isinstance(body.get("message"), dict):
        raise ProviderError(
            "ai_invalid_response", "The provider returned an unexpected response."
        )
    text = body["message"].get("content")
    if not isinstance(text, str):
        raise ProviderError(
            "ai_invalid_response", "The provider returned an unexpected response."
        )
    input_tokens = body.get("prompt_eval_count")
    output_tokens = body.get("eval_count")
    return ProviderReply(
        text,
        input_tokens if isinstance(input_tokens, int) and not isinstance(input_tokens, bool) else None,
        output_tokens if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) else None,
        None,
    )


def _openai_chat(
    spec: ProviderSpec,
    base_url: str,
    model: str,
    system_prompt: str,
    user_text: str,
    image_b64: str | None,
    api_key: str | None,
    temperature: float,
    timeout: float,
    json_mode: bool,
) -> ProviderReply:
    if image_b64:
        user_content: Any = [
            {"type": "text", "text": user_text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]
    else:
        user_content = user_text
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "stream": False,
    }
    # Only Ollama has a broadly supported JSON flag. OpenAI-compatible servers
    # differ, so the prompt itself asks for JSON instead of risking a 400.
    _status, body = _request_json(
        f"{base_url}{OPENAI_CHAT_SUFFIX}",
        headers=_auth_headers(spec, api_key),
        payload=payload,
        timeout=timeout,
    )
    if not isinstance(body, dict):
        raise ProviderError(
            "ai_invalid_response", "The provider returned an unexpected response."
        )
    choices = body.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    text = _content_text(content, "openai")
    input_tokens, output_tokens, total_tokens = _usage_from_openai(body)
    return ProviderReply(text, input_tokens, output_tokens, total_tokens)


def _anthropic_chat(
    base_url: str,
    model: str,
    system_prompt: str,
    user_text: str,
    image_b64: str | None,
    api_key: str | None,
    temperature: float,
    timeout: float,
    json_mode: bool,
) -> ProviderReply:
    content: list[dict[str, Any]] = []
    if image_b64:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            }
        )
    content.append({"type": "text", "text": user_text})
    payload = {
        "model": model,
        "max_tokens": 8192,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": content}],
    }
    _status, body = _request_json(
        f"{base_url}/messages",
        headers=_auth_headers(get_provider("anthropic"), api_key),
        payload=payload,
        timeout=timeout,
    )
    if not isinstance(body, dict):
        raise ProviderError(
            "ai_invalid_response", "The provider returned an unexpected response."
        )
    blocks = body.get("content")
    if not isinstance(blocks, list):
        raise ProviderError(
            "ai_invalid_response", "The provider returned an unexpected response."
        )
    text = "".join(
        block["text"]
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    )
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    return ProviderReply(
        text,
        input_tokens if isinstance(input_tokens, int) and not isinstance(input_tokens, bool) else None,
        output_tokens if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) else None,
        None,
    )


def _gemini_chat(
    base_url: str,
    model: str,
    system_prompt: str,
    user_text: str,
    image_b64: str | None,
    api_key: str | None,
    temperature: float,
    timeout: float,
    json_mode: bool,
) -> ProviderReply:
    model_id = model[len("models/") :] if model.startswith("models/") else model
    parts: list[dict[str, Any]] = [{"text": user_text}]
    if image_b64:
        parts.append(
            {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": image_b64,
                }
            }
        )
    generation_config: dict[str, Any] = {"temperature": temperature}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation_config,
    }
    _status, body = _request_json(
        f"{base_url}/models/{urllib_parse.quote(model_id, safe='')}:generateContent",
        headers=_auth_headers(get_provider("gemini"), api_key),
        payload=payload,
        timeout=timeout,
    )
    if not isinstance(body, dict):
        raise ProviderError(
            "ai_invalid_response", "The provider returned an unexpected response."
        )
    candidates = body.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else None
    content = first.get("content") if isinstance(first, dict) else None
    parts_out = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts_out, list):
        raise ProviderError(
            "ai_invalid_response", "The provider returned an unexpected response."
        )
    text = "".join(
        part["text"] for part in parts_out if isinstance(part, dict) and isinstance(part.get("text"), str)
    )
    usage = body.get("usageMetadata") if isinstance(body.get("usageMetadata"), dict) else {}
    input_tokens = usage.get("promptTokenCount")
    output_tokens = usage.get("candidatesTokenCount")
    total_tokens = usage.get("totalTokenCount")
    return ProviderReply(
        text,
        input_tokens if isinstance(input_tokens, int) and not isinstance(input_tokens, bool) else None,
        output_tokens if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) else None,
        total_tokens if isinstance(total_tokens, int) and not isinstance(total_tokens, bool) else None,
    )


def complete(
    provider_id: str,
    *,
    base_url: str,
    model: str,
    system_prompt: str,
    user_text: str,
    api_key: str | None,
    image_b64: str | None = None,
    temperature: float = 0.0,
    timeout: float = DEFAULT_TIMEOUT,
    json_mode: bool = False,
) -> ProviderReply:
    """Run one text or vision generation through the selected adapter."""
    spec = get_provider(provider_id)
    model = model.strip()
    if not model:
        raise ProviderError(
            "ai_model_required",
            "Choose a model for this task before using AI assistance.",
            category="config",
        )
    started = time.monotonic()
    if spec.kind == "ollama":
        reply = _ollama_chat(
            base_url,
            model,
            system_prompt,
            user_text,
            image_b64,
            api_key,
            temperature,
            timeout,
            json_mode,
        )
    elif spec.kind == "anthropic":
        reply = _anthropic_chat(
            base_url,
            model,
            system_prompt,
            user_text,
            image_b64,
            api_key,
            temperature,
            timeout,
            json_mode,
        )
    elif spec.kind == "gemini":
        reply = _gemini_chat(
            base_url,
            model,
            system_prompt,
            user_text,
            image_b64,
            api_key,
            temperature,
            timeout,
            json_mode,
        )
    else:
        reply = _openai_chat(
            spec,
            base_url,
            model,
            system_prompt,
            user_text,
            image_b64,
            api_key,
            temperature,
            timeout,
            json_mode,
        )
    logger.debug(
        "AI request completed provider=%s model=%s duration_ms=%d",
        provider_id,
        model,
        int((time.monotonic() - started) * 1000),
    )
    return reply
