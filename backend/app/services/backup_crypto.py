"""Optional password protection for downloaded project backups.

A plain backup zip is convenient but readable by anyone who can open the file.
This module wraps that zip in an authenticated, password-encrypted container so a
copy stored off-device is not plain text plus images.

Design constraints:

- The password is never stored, logged or written into the archive. It is used to
  derive a key for one download, then discarded. Losing the password means losing
  access, so the UI asks for confirmation before downloading.
- Encryption is opt-in per download. Vault copies and automatic copies stay
  plaintext, because those run without a user present and a stored password would
  be worse than no encryption.
- The container uses AES-256-GCM per chunk with a scrypt-derived key. A key-check
  record in the header distinguishes a wrong password from a damaged file, and
  each chunk is authenticated with the header and its index as associated data, so
  a truncated, reordered or edited archive fails instead of decrypting to garbage.
- No compression is applied here: the payload is already a deflated zip, and not
  re-compressing keeps the encrypted size close to the plaintext size, so the
  existing upload limit still bounds the work a restore can cause.
"""

from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.errors import AppError

# File magic and container version. A reader rejects anything else instead of
# guessing, so a renamed or corrupted file cannot be half-decrypted.
MAGIC = b"DRBZ"
FORMAT_VERSION = 1
ENCRYPTED_SUFFIX = ".drbz"

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024

_SALT_SIZE = 16
_NONCE_PREFIX_SIZE = 8
_KEY_SIZE = 32
_TAG_SIZE = 16
_CHUNK_SIZE = 1024 * 1024

# A record under this counter proves the derived key is the right one. Chunk
# counters start at zero, so they can never collide with it.
_CHECK_COUNTER = 0xFFFFFFFF
_KEY_CHECK = b"docurebuild-backup-v1"

_BASE_HEADER_SIZE = len(MAGIC) + 1 + _SALT_SIZE + _NONCE_PREFIX_SIZE
_CHECK_SIZE = len(_KEY_CHECK) + _TAG_SIZE
_HEADER_SIZE = _BASE_HEADER_SIZE + _CHECK_SIZE

# The header is fixed-size, so a reader can validate a container before deriving
# a key. Exposed for tests and for callers that inspect the format.
HEADER_SIZE = _HEADER_SIZE
# Exposed so a caller or test can reason about the container's record size.
CHUNK_SIZE = _CHUNK_SIZE

# scrypt cost. 2**15 with r=8 needs about 32 MiB and well under a second on a
# desktop, which is a reasonable trade for a file the user decrypts rarely.
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def validate_password(password: str) -> None:
    """Reject a password that is too short to be worth deriving a key from."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise AppError(
            422,
            "backup_password_too_short",
            f"Use a password of at least {MIN_PASSWORD_LENGTH} characters.",
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AppError(
            422,
            "backup_password_too_long",
            f"Use a password of at most {MAX_PASSWORD_LENGTH} characters.",
        )


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_SIZE,
        maxmem=_SCRYPT_MAXMEM,
    )


def _nonce(prefix: bytes, index: int) -> bytes:
    return prefix + struct.pack(">I", index)


def _chunk_aad(header: bytes, index: int) -> bytes:
    # Binding the index prevents an attacker from reordering or dropping chunks.
    return header + struct.pack(">I", index)


def is_encrypted(path: Path) -> bool:
    """Whether a file starts with the encrypted-container magic."""
    try:
        with path.open("rb") as handle:
            return handle.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def encrypt_file(source: Path, target: Path, password: str) -> None:
    """Encrypt ``source`` into ``target``, replacing ``target`` atomically."""
    validate_password(password)
    salt = os.urandom(_SALT_SIZE)
    prefix = os.urandom(_NONCE_PREFIX_SIZE)
    base_header = MAGIC + bytes([FORMAT_VERSION]) + salt + prefix
    cipher = AESGCM(_derive_key(password, salt))
    check = cipher.encrypt(_nonce(prefix, _CHECK_COUNTER), _KEY_CHECK, base_header)
    header = base_header + check
    temporary = target.with_name(f"{target.name}.part")
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            writer.write(header)
            index = 0
            while True:
                chunk = reader.read(_CHUNK_SIZE)
                if not chunk:
                    break
                sealed = cipher.encrypt(_nonce(prefix, index), chunk, _chunk_aad(header, index))
                writer.write(struct.pack(">I", len(sealed)))
                writer.write(sealed)
                index += 1
            # A zero-length record marks a complete archive, so a truncated file
            # cannot be mistaken for a shorter valid one.
            writer.write(struct.pack(">I", 0))
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise


def decrypt_file(source: Path, target: Path, password: str) -> None:
    """Decrypt ``source`` into ``target``, raising a typed error on failure."""
    temporary = target.with_name(f"{target.name}.part")
    try:
        with source.open("rb") as reader:
            header = reader.read(_HEADER_SIZE)
            if len(header) < _HEADER_SIZE or not header.startswith(MAGIC):
                raise AppError(
                    422,
                    "backup_invalid",
                    "This file is not an encrypted DocuRebuild backup.",
                )
            version = header[len(MAGIC)]
            if version != FORMAT_VERSION:
                raise AppError(
                    422,
                    "backup_incompatible",
                    "This encrypted backup uses an unsupported format version.",
                )
            salt_start = len(MAGIC) + 1
            salt = header[salt_start : salt_start + _SALT_SIZE]
            prefix = header[salt_start + _SALT_SIZE : _BASE_HEADER_SIZE]
            base_header = header[:_BASE_HEADER_SIZE]
            cipher = AESGCM(_derive_key(password, salt))
            try:
                cipher.decrypt(
                    _nonce(prefix, _CHECK_COUNTER),
                    header[_BASE_HEADER_SIZE:],
                    base_header,
                )
            except InvalidTag as exc:
                # The key-check record is the only reliable way to tell a wrong
                # password from a damaged payload, so this check runs first.
                raise AppError(
                    422,
                    "backup_wrong_password",
                    "The password is incorrect for this backup.",
                ) from exc

            with temporary.open("wb") as writer:
                index = 0
                while True:
                    raw_length = reader.read(4)
                    if len(raw_length) != 4:
                        raise AppError(
                            422,
                            "backup_corrupt",
                            "The encrypted backup is incomplete.",
                        )
                    length = struct.unpack(">I", raw_length)[0]
                    if length == 0:
                        break
                    if length < _TAG_SIZE or length > _CHUNK_SIZE + _TAG_SIZE:
                        raise AppError(
                            422,
                            "backup_corrupt",
                            "The encrypted backup is damaged.",
                        )
                    sealed = reader.read(length)
                    if len(sealed) != length:
                        raise AppError(
                            422,
                            "backup_corrupt",
                            "The encrypted backup is incomplete.",
                        )
                    try:
                        plain = cipher.decrypt(
                            _nonce(prefix, index), sealed, _chunk_aad(header, index)
                        )
                    except InvalidTag as exc:
                        raise AppError(
                            422,
                            "backup_corrupt",
                            "The encrypted backup is damaged.",
                        ) from exc
                    writer.write(plain)
                    index += 1
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
