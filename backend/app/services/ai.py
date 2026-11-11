from __future__ import annotations

import ipaddress
import json
import socket
import uuid
from pathlib import Path
from typing import Any, NamedTuple
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from pydantic import ValidationError

from app.core.errors import AppError
from app.db.project_schema import project_db, utc_iso
from app.schemas.ai import AiProviderKind, AiSuggestionStatus
from app.schemas.settings import AiProfileSettings
from app.services import ocr as ocr_service

# Only local inference servers are supported in this phase. Both are optional
# and require an explicit connection test and model choice from the user.
PROVIDERS: tuple[dict[str, str], ...] = (
    {"id": "ollama", "default_base_url": "http://127.0.0.1:11434"},
    {"id": "openai_compatible", "default_base_url": "http://127.0.0.1:1234/v1"},
)
DEFAULT_BASE_URLS = {item["id"]: item["default_base_url"] for item in PROVIDERS}

MAX_RESPONSE_BYTES = 1_000_000
MAX_TEXT_LENGTH = 20_000
PROBE_TIMEOUT = 5.0
GENERATE_TIMEOUT = 60.0
USER_AGENT = "DocuRebuild/0.1"

SYSTEM_PROMPT = (
    "You correct OCR text for a document reconstruction tool. "
    "Return only the corrected text and nothing else. "
    "Do not translate, summarize, explain, reorder or add content. "
    "Preserve line breaks, punctuation, numbers and the original language. "
    "If a character is genuinely unreadable, keep the original character."
)


class _FetchFailure(Exception):
    def __init__(
        self,
        status: str,
        error_code: str,
        http_status: int | None = None,
    ) -> None:
        super().__init__(status)
        self.status = status
        self.error_code = error_code
        self.http_status = http_status


class Completion(NamedTuple):
    text: str
    provider: AiProviderKind
    model: str
    base_url: str


def provider_catalog() -> list[dict[str, str]]:
    return [dict(item) for item in PROVIDERS]


def default_base_url(provider: AiProviderKind) -> str:
    return DEFAULT_BASE_URLS[provider]


def normalize_base_url(
    provider: AiProviderKind,
    value: str,
    *,
    allow_remote: bool = False,
) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        cleaned = default_base_url(provider)
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AppError(422, "invalid_ai_settings", "The AI server URL is not valid.")
    if parsed.username or parsed.password:
        raise AppError(
            422,
            "invalid_ai_settings",
            "The AI server URL must not contain credentials.",
        )
    # Block the well-known cloud metadata endpoints. AI servers are expected to
    # be local or user-owned, never a metadata service.
    if (parsed.hostname or "").lower() in {"169.254.169.254", "metadata.google.internal"}:
        raise AppError(422, "invalid_ai_settings", "That AI server address is not allowed.")
    if not _is_loopback(parsed.hostname) and not allow_remote:
        raise AppError(
            403,
            "ai_remote_not_allowed",
            "This server is not on loopback. Enable remote AI consent in Settings first.",
        )
    if provider == "openai_compatible" and not cleaned.endswith("/v1"):
        cleaned = f"{cleaned}/v1"
    return cleaned


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


def _decode_json(raw: bytes) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _FetchFailure("invalid_response", "ai_invalid_response") from exc


def _read_json(
    url: str,
    timeout: float,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib_request.Request(
        url,
        data=data,
        headers=headers,
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise _FetchFailure("invalid_response", "ai_invalid_response")
            return response.status, _decode_json(raw)
    except urllib_error.HTTPError as exc:
        raise _FetchFailure("http_error", "ai_http_error", exc.code) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise _FetchFailure("timeout", "ai_timeout") from exc
    except urllib_error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise _FetchFailure("timeout", "ai_timeout") from exc
        raise _FetchFailure("unreachable", "ai_unreachable") from exc
    except (OSError, ValueError) as exc:
        raise _FetchFailure("unreachable", "ai_unreachable") from exc


def _model_entry(
    model_id: str,
    family: str | None = None,
    parameter_size: str | None = None,
) -> dict[str, Any]:
    return {"id": model_id, "family": family, "parameter_size": parameter_size}


def _ollama_models(base_url: str) -> tuple[list[dict[str, Any]], str | None]:
    _status, body = _read_json(f"{base_url}/api/tags", PROBE_TIMEOUT)
    if not isinstance(body, dict) or not isinstance(body.get("models"), list):
        raise _FetchFailure("invalid_response", "ai_invalid_response")
    models: list[dict[str, Any]] = []
    for item in body["models"]:
        if not isinstance(item, dict):
            continue
        model_id = item.get("model") or item.get("name")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        family = details.get("family")
        parameter_size = details.get("parameter_size")
        models.append(
            _model_entry(
                model_id.strip(),
                family if isinstance(family, str) else None,
                parameter_size if isinstance(parameter_size, str) else None,
            )
        )
    models.sort(key=lambda entry: entry["id"].lower())
    version = None
    try:
        _version_status, version_body = _read_json(f"{base_url}/api/version", PROBE_TIMEOUT)
        if isinstance(version_body, dict) and isinstance(version_body.get("version"), str):
            version = version_body["version"]
    except _FetchFailure:
        # Version reporting is optional; model discovery is what matters.
        version = None
    return models, version


def _openai_models(base_url: str) -> list[dict[str, Any]]:
    _status, body = _read_json(f"{base_url}/models", PROBE_TIMEOUT)
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise _FetchFailure("invalid_response", "ai_invalid_response")
    models: list[dict[str, Any]] = []
    for item in body["data"]:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        models.append(_model_entry(model_id.strip()))
    models.sort(key=lambda entry: entry["id"].lower())
    return models


def probe_provider(
    provider: AiProviderKind,
    base_url: str = "",
    *,
    allow_remote: bool = False,
) -> dict[str, Any]:
    """Inspect a local server only when the user asks for a connection test.

    Expected failures are returned as a status instead of raised so Settings can
    explain what happened without pretending the server is ready.
    """
    resolved = normalize_base_url(provider, base_url, allow_remote=allow_remote)
    try:
        if provider == "ollama":
            models, version = _ollama_models(resolved)
        else:
            models = _openai_models(resolved)
            version = None
    except _FetchFailure as exc:
        return {
            "status": exc.status,
            "provider": provider,
            "base_url": resolved,
            "models": [],
            "version": None,
            "error_code": exc.error_code,
            "http_status": exc.http_status,
        }
    return {
        "status": "ready",
        "provider": provider,
        "base_url": resolved,
        "models": models,
        "version": version,
        "error_code": None,
        "http_status": None,
    }


def _resolve_profile(
    profile: AiProfileSettings,
    *,
    provider: AiProviderKind | None,
    base_url: str | None,
    model: str | None,
) -> tuple[AiProviderKind, str, str]:
    resolved_provider = provider or profile.provider
    resolved_model = (model if model is not None else profile.model).strip()
    if not resolved_model:
        raise AppError(
            409,
            "ai_not_configured",
            "Choose a local AI model in Settings before using AI assistance.",
        )
    try:
        resolved = AiProfileSettings(
            provider=resolved_provider,
            base_url=base_url if base_url is not None else profile.base_url,
            model=resolved_model,
            allow_remote=profile.allow_remote,
        )
    except ValidationError as exc:
        raise AppError(422, "invalid_ai_settings", "The AI settings are not valid.") from exc
    return (
        resolved.provider,
        normalize_base_url(
            resolved.provider,
            resolved.base_url,
            allow_remote=resolved.allow_remote,
        ),
        resolved.model,
    )


def _chat_completion(
    provider: AiProviderKind,
    base_url: str,
    model: str,
    text: str,
) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    try:
        if provider == "ollama":
            _status, body = _read_json(
                f"{base_url}/api/chat",
                GENERATE_TIMEOUT,
                {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
            message = body.get("message") if isinstance(body, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
        else:
            _status, body = _read_json(
                f"{base_url}/chat/completions",
                GENERATE_TIMEOUT,
                {
                    "model": model,
                    "messages": messages,
                    "temperature": 0,
                    "stream": False,
                },
            )
            choices = body.get("choices") if isinstance(body, dict) else None
            first = choices[0] if isinstance(choices, list) and choices else None
            message = first.get("message") if isinstance(first, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
    except _FetchFailure as exc:
        raise AppError(
            502,
            exc.error_code,
            "The configured local AI server could not complete the request.",
        ) from exc

    if not isinstance(content, str):
        raise AppError(
            502,
            "ai_invalid_response",
            "The configured local AI server returned an unexpected response.",
        )
    cleaned = content.strip()
    if not cleaned:
        raise AppError(
            502,
            "ai_empty_response",
            "The configured local AI server returned no text.",
        )
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise AppError(
            502,
            "ai_text_too_long",
            "The AI response was too long to store as a proposal.",
        )
    return cleaned


def request_cleanup(
    profile: AiProfileSettings,
    text: str,
    *,
    provider: AiProviderKind | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> Completion:
    if not text.strip():
        raise AppError(422, "ocr_block_empty", "This OCR block has no text to review.")
    if len(text) > MAX_TEXT_LENGTH:
        raise AppError(422, "ai_text_too_long", "This OCR block is too long for one AI request.")
    resolved_provider, resolved_url, resolved_model = _resolve_profile(
        profile,
        provider=provider,
        base_url=base_url,
        model=model,
    )
    cleaned = _chat_completion(resolved_provider, resolved_url, resolved_model, text)
    return Completion(cleaned, resolved_provider, resolved_model, resolved_url)


def _get_page(conn, page_id: str):
    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if row is None:
        raise AppError(404, "page_not_found", "Page not found.")
    return row


def _load_block(conn, page_id: str, block_id: str):
    """Return the page, OCR block and run, refusing stale or unfinished results."""
    page = _get_page(conn, page_id)
    block = conn.execute(
        "SELECT * FROM ocr_blocks WHERE id = ? AND page_id = ?",
        (block_id, page_id),
    ).fetchone()
    if block is None:
        raise AppError(404, "ocr_block_not_found", "OCR text block not found.")
    run = conn.execute("SELECT * FROM ocr_runs WHERE id = ?", (block["run_id"],)).fetchone()
    if run is None:
        raise AppError(404, "ocr_run_not_found", "OCR run not found.")
    if run["status"] != "succeeded":
        raise AppError(409, "ocr_not_ready", "OCR has not finished for this page.")
    current_asset = page["display_asset_id"] or page["original_asset_id"]
    if run["source_asset_id"] != current_asset or int(run["rotation"]) != int(page["rotation"]):
        raise AppError(
            409,
            "ocr_stale",
            "The OCR result no longer matches the page. Run OCR again.",
        )
    return page, block, run


def _suggestion_payload(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "page_id": row["page_id"],
        "block_id": row["block_id"],
        "task": row["task"],
        "original_text": row["original_text"],
        "proposed_text": row["proposed_text"],
        "provider": row["provider"],
        "model": row["model"],
        "base_url": row["base_url"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_page_suggestions(
    project_dir: Path,
    page_id: str,
    status: AiSuggestionStatus | None = None,
) -> list[dict[str, Any]]:
    if status is not None and status not in {"pending", "accepted", "rejected"}:
        raise AppError(422, "invalid_ai_suggestion_status", "Unknown proposal status.")
    with project_db(project_dir) as conn:
        _get_page(conn, page_id)
        if status is None:
            rows = conn.execute(
                "SELECT * FROM ai_suggestions WHERE page_id = ? ORDER BY created_at DESC",
                (page_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM ai_suggestions
                WHERE page_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (page_id, status),
            ).fetchall()
    return [_suggestion_payload(row) for row in rows]


def create_cleanup_suggestion(
    project_dir: Path,
    page_id: str,
    block_id: str,
    profile: AiProfileSettings,
    *,
    provider: AiProviderKind | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with project_db(project_dir) as conn:
        _page, block, _run = _load_block(conn, page_id, block_id)
        original = block["text"] or ""
        run_id = block["run_id"]

    # The network call happens outside the database transaction.
    completion = request_cleanup(
        profile,
        original,
        provider=provider,
        base_url=base_url,
        model=model,
    )

    now = utc_iso()
    suggestion_id = str(uuid.uuid4())
    with project_db(project_dir) as conn:
        # Re-read so a manual correction made during the request is never
        # overwritten by a proposal based on older text.
        _page, block, _run = _load_block(conn, page_id, block_id)
        if (block["text"] or "") != original:
            raise AppError(
                409,
                "ai_suggestion_stale",
                "The OCR text changed while the AI proposal was being generated.",
            )
        conn.execute(
            """
            INSERT INTO ai_suggestions (id, page_id, block_id, task, original_text,
                                        proposed_text, provider, model, base_url,
                                        status, created_at, updated_at)
            VALUES (?, ?, ?, 'ocr_cleanup', ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                suggestion_id,
                page_id,
                block_id,
                original,
                completion.text,
                completion.provider,
                completion.model,
                completion.base_url,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        suggestion = _suggestion_payload(row)

    return suggestion, ocr_service.get_run(project_dir, run_id)


def decide_suggestion(
    project_dir: Path,
    suggestion_id: str,
    status: AiSuggestionStatus,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if status not in {"accepted", "rejected"}:
        raise AppError(422, "invalid_ai_suggestion_status", "Unknown proposal decision.")
    with project_db(project_dir) as conn:
        suggestion = conn.execute(
            "SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        if suggestion is None:
            raise AppError(404, "ai_suggestion_not_found", "AI proposal not found.")
        if suggestion["status"] != "pending":
            raise AppError(
                409,
                "ai_suggestion_not_pending",
                "This AI proposal was already reviewed.",
            )
        page_id = suggestion["page_id"]
        block_id = suggestion["block_id"]
        if status == "accepted":
            _page, block, run = _load_block(conn, page_id, block_id)
            if (block["text"] or "") != suggestion["original_text"]:
                raise AppError(
                    409,
                    "ai_suggestion_stale",
                    "The OCR text changed after this AI proposal was created.",
                )
            run_id = run["id"]
        else:
            block = conn.execute(
                "SELECT * FROM ocr_blocks WHERE id = ?", (block_id,)
            ).fetchone()
            if block is None:
                raise AppError(404, "ocr_block_not_found", "OCR text block not found.")
            run_id = block["run_id"]

    if status == "accepted":
        run_payload = ocr_service.update_block(
            project_dir,
            page_id,
            block_id,
            text=suggestion["proposed_text"],
        )
    else:
        # Rejecting only discards the proposal, so it stays possible even when
        # the page changed after the proposal was created.
        run_payload = ocr_service.get_run(project_dir, run_id)

    with project_db(project_dir) as conn:
        conn.execute(
            "UPDATE ai_suggestions SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_iso(), suggestion_id),
        )
        updated = conn.execute(
            "SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        return _suggestion_payload(updated), run_payload
