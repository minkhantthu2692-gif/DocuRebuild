from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

# Legacy task slots remain readable so an explicit migration can copy them.
TASKS = ("text", "vision")
MAX_API_KEY_LENGTH = 1024
# A secret id is an internal, non-secret handle such as `connkey:<uuid>`.
SECRET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:._-]{0,80}$")

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
        secret_id: value
        for secret_id, value in decoded.items()
        if isinstance(secret_id, str)
        and SECRET_ID_PATTERN.fullmatch(secret_id)
        and isinstance(value, str)
        and value
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
    """Return the decrypted key for a legacy task slot, or None."""
    if task not in TASKS:
        raise ValueError(f"Unknown AI task profile: {task}")
    return get_secret(task)


def has_api_key(task: str) -> bool:
    if task not in TASKS:
        raise ValueError(f"Unknown AI task profile: {task}")
    return has_secret(task)


def set_api_key(task: str, value: str) -> None:
    if task not in TASKS:
        raise ValueError(f"Unknown AI task profile: {task}")
    set_secret(task, value)


def clear_api_key(task: str) -> None:
    if task not in TASKS:
        raise ValueError(f"Unknown AI task profile: {task}")
    clear_secret(task)


def _check_secret_id(secret_id: str) -> str:
    if not isinstance(secret_id, str) or not SECRET_ID_PATTERN.fullmatch(secret_id):
        raise ValueError("Invalid AI secret id.")
    return secret_id


def get_secret(secret_id: str) -> str | None:
    """Return one decrypted secret by internal id, or None when absent."""
    _check_secret_id(secret_id)
    with _lock:
        return _read_store().get(secret_id)


def has_secret(secret_id: str) -> bool:
    _check_secret_id(secret_id)
    with _lock:
        return _read_store().get(secret_id) is not None


def set_secret(secret_id: str, value: str) -> None:
    """Store one secret (for example a connection key) in the encrypted vault."""
    _check_secret_id(secret_id)
    cleaned = clean_api_key(value)
    with _lock:
        values = _read_store()
        values[secret_id] = cleaned
        _write_store(values)


def clear_secret(secret_id: str) -> None:
    _check_secret_id(secret_id)
    with _lock:
        values = _read_store()
        if values.pop(secret_id, None) is not None:
            _write_store(values)


def copy_secret(source_id: str, target_id: str) -> bool:
    """Copy an encrypted value inside the vault without exposing it to callers."""
    _check_secret_id(source_id)
    _check_secret_id(target_id)
    with _lock:
        values = _read_store()
        value = values.get(source_id)
        if value is None:
            return False
        values[target_id] = value
        _write_store(values)
        return True
