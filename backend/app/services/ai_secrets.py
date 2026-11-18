from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

# One key per task profile, the same slots the settings page edits.
TASKS = ("text", "vision")
MAX_API_KEY_LENGTH = 1024

_lock = threading.Lock()


def _secrets_dir() -> Path:
    path = get_settings().data_dir / "secrets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _restrict(path: Path) -> None:
    """Best-effort owner-only permission; NTFS ACLs still apply on Windows."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _master_key() -> bytes:
    path = _secrets_dir() / "ai_keys.key"
    if path.exists():
        raw = path.read_bytes().strip()
        if raw:
            return raw
    key = Fernet.generate_key()
    path.write_bytes(key)
    _restrict(path)
    return key


def _store_path() -> Path:
    return _secrets_dir() / "ai_keys.enc"


def _read_store() -> dict[str, str]:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        token = path.read_bytes()
        if not token:
            return {}
        decoded = json.loads(Fernet(_master_key()).decrypt(token))
    except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        # A lost or replaced master key makes stored values unreadable. Treat the
        # store as empty instead of blocking the whole settings page; the user can
        # enter the key again, which rewrites the store.
        logger.warning("Stored AI credentials could not be decrypted.")
        return {}
    except OSError:
        # An unreadable data folder must not break Settings either.
        logger.warning("Stored AI credentials could not be read.")
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {
        task: value
        for task, value in decoded.items()
        if task in TASKS and isinstance(value, str) and value
    }


def _write_store(values: dict[str, str]) -> None:
    path = _store_path()
    try:
        token = Fernet(_master_key()).encrypt(
            json.dumps(values, ensure_ascii=False).encode("utf-8")
        )
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(token)
        _restrict(temporary)
        temporary.replace(path)
        _restrict(path)
    except OSError as exc:
        raise AppError(
            500,
            "ai_key_store_failed",
            "The API key could not be saved in the local data folder.",
        ) from exc


def clean_api_key(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise AppError(
            422,
            "ai_api_key_empty",
            "Enter an API key or remove the saved one instead.",
        )
    if len(cleaned) > MAX_API_KEY_LENGTH:
        raise AppError(422, "ai_api_key_too_long", "This API key is too long to store.")
    if any(character.isspace() for character in cleaned) or "\x00" in cleaned:
        raise AppError(
            422,
            "ai_api_key_invalid",
            "An API key must be one line without spaces.",
        )
    if not cleaned.isascii() or not cleaned.isprintable():
        raise AppError(
            422,
            "ai_api_key_invalid",
            "An API key must use printable ASCII characters.",
        )
    return cleaned


def get_api_key(task: str) -> str | None:
    """Return the decrypted key for a task, or None when none is stored."""
    if task not in TASKS:
        raise ValueError(f"Unknown AI task profile: {task}")
    with _lock:
        return _read_store().get(task)


def has_api_key(task: str) -> bool:
    if task not in TASKS:
        raise ValueError(f"Unknown AI task profile: {task}")
    with _lock:
        return _read_store().get(task) is not None


def set_api_key(task: str, value: str) -> None:
    if task not in TASKS:
        raise ValueError(f"Unknown AI task profile: {task}")
    cleaned = clean_api_key(value)
    with _lock:
        values = _read_store()
        values[task] = cleaned
        _write_store(values)


def clear_api_key(task: str) -> None:
    if task not in TASKS:
        raise ValueError(f"Unknown AI task profile: {task}")
    with _lock:
        values = _read_store()
        if values.pop(task, None) is not None:
            _write_store(values)
