from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.core.errors import AppError
from app.services import backup_crypto
from tests.conftest import upload_pages

PASSWORD = "correct horse battery"


def _save_document(client: TestClient, project_id: str, text: str) -> None:
    response = client.put(
        f"/api/projects/{project_id}/document",
        json={
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": text}],
                    }
                ],
            },
            "plain_text": text,
        },
    )
    assert response.status_code == 200, response.text


def _encrypted_backup(
    client: TestClient, project_id: str, password: str = PASSWORD
) -> bytes:
    response = client.post(
        f"/api/projects/{project_id}/backup", json={"password": password}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/octet-stream"
    disposition = response.headers["content-disposition"]
    assert "attachment;" in disposition
    assert ".drbz" in disposition
    return response.content


def _restore(
    client: TestClient,
    content: bytes,
    *,
    name: str = "book-backup.drbz",
    password: str | None = None,
) -> Response:
    data = {"password": password} if password is not None else None
    return client.post(
        "/api/projects/restore",
        files={"file": (name, content, "application/octet-stream")},
        data=data,
    )


def test_encrypted_backup_round_trips_through_restore(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "Encrypted chapter")
    upload_pages(client, project_id, ["page-1.png"])

    content = _encrypted_backup(client, project_id)

    # The delivered file is a container, not a readable zip: neither the zip
    # signature nor any entry name appears in it.
    assert content.startswith(backup_crypto.MAGIC)
    assert b"PK\x03\x04" not in content
    assert b"project.db" not in content

    response = _restore(client, content, password=PASSWORD)
    assert response.status_code == 201, response.text
    restored = response.json()
    assert restored["id"] != project_id
    assert restored["name"] == "Quantum Mechanics (restored)"
    assert restored["page_count"] == 1
    document = client.get(f"/api/projects/{restored['id']}/document").json()
    assert document["plain_text"] == "Encrypted chapter"
    # The source project is untouched.
    assert client.get(f"/api/projects/{project_id}").status_code == 200


def test_encrypted_backup_requires_its_own_password(
    client: TestClient, project: dict
) -> None:
    content = _encrypted_backup(client, project["id"])

    missing = _restore(client, content)
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "backup_password_required"

    wrong = _restore(client, content, password="not the right password")
    assert wrong.status_code == 422
    assert wrong.json()["detail"]["code"] == "backup_wrong_password"

    # A failed attempt must not leave a half-restored project behind.
    names = [item["name"] for item in client.get("/api/projects").json()]
    assert names == ["Quantum Mechanics"]


def test_short_password_is_refused(client: TestClient, project: dict) -> None:
    response = client.post(
        f"/api/projects/{project['id']}/backup", json={"password": "short"}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_password_too_short"


def test_damaged_encrypted_backup_is_rejected(
    client: TestClient, project: dict
) -> None:
    content = _encrypted_backup(client, project["id"])

    # Flip one ciphertext byte after the fixed header. The key is right, so the
    # failure is reported as damage rather than a wrong password.
    damaged = bytearray(content)
    damaged[backup_crypto.HEADER_SIZE + 8] ^= 0x01
    response = _restore(client, bytes(damaged), password=PASSWORD)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_corrupt"

    # Dropping the end marker makes the stream incomplete.
    truncated = content[: -4]
    response = _restore(client, truncated, password=PASSWORD)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_corrupt"


def test_plain_zip_restores_even_if_a_password_is_supplied(
    client: TestClient, project: dict
) -> None:
    _save_document(client, project["id"], "Plain chapter")
    plain = client.get(f"/api/projects/{project['id']}/backup")
    assert plain.status_code == 200
    assert plain.content.startswith(b"PK\x03\x04")

    response = _restore(
        client,
        plain.content,
        name="book-backup.zip",
        password="an unused password",
    )
    assert response.status_code == 201, response.text
    restored = response.json()
    assert (
        client.get(f"/api/projects/{restored['id']}/document").json()["plain_text"]
        == "Plain chapter"
    )


def test_vault_copies_stay_plaintext(client: TestClient, project: dict) -> None:
    # Automatic and vault copies run without a user present, so they are never
    # encrypted; only an explicit download can be protected.
    created = client.post(f"/api/projects/{project['id']}/backups")
    assert created.status_code == 201, created.text
    filename = created.json()["filename"]

    download = client.get(
        f"/api/projects/{project['id']}/backups/{filename}"
    )
    assert download.status_code == 200
    assert download.content.startswith(b"PK\x03\x04")


def test_crypto_container_round_trip_across_chunks(tmp_path: Path) -> None:
    # More than two chunk boundaries, so the counter and AAD are exercised.
    payload = os.urandom(backup_crypto.CHUNK_SIZE * 2 + 137)
    source = tmp_path / "source.bin"
    source.write_bytes(payload)
    sealed = tmp_path / "sealed.drbz"
    opened = tmp_path / "opened.bin"

    backup_crypto.encrypt_file(source, sealed, PASSWORD)

    assert backup_crypto.is_encrypted(sealed)
    assert not backup_crypto.is_encrypted(source)
    assert sealed.read_bytes() != payload

    backup_crypto.decrypt_file(sealed, opened, PASSWORD)
    assert opened.read_bytes() == payload


def test_crypto_rejects_a_wrong_password(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"some backup bytes")
    sealed = tmp_path / "sealed.drbz"
    backup_crypto.encrypt_file(source, sealed, PASSWORD)

    with pytest.raises(AppError) as caught:
        backup_crypto.decrypt_file(sealed, tmp_path / "out.bin", "wrong password")
    assert caught.value.code == "backup_wrong_password"
    # A failed decrypt never leaves a partial output file behind.
    assert not (tmp_path / "out.bin").exists()


def test_crypto_rejects_a_non_container(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    source.write_bytes(b"PK\x03\x04 not an encrypted container")
    assert not backup_crypto.is_encrypted(source)

    with pytest.raises(AppError) as caught:
        backup_crypto.decrypt_file(source, tmp_path / "out.bin", PASSWORD)
    assert caught.value.code == "backup_invalid"
