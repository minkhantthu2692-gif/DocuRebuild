from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import Response

from tests.conftest import upload_pages


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


def _backup(client: TestClient, project_id: str) -> tuple[bytes, str]:
    response = client.get(f"/api/projects/{project_id}/backup")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment;" in response.headers["content-disposition"]
    assert ".zip" in response.headers["content-disposition"]
    return response.content, response.headers["content-disposition"]


def _restore(
    client: TestClient, content: bytes, name: str = "book-backup.zip"
) -> Response:
    return client.post(
        "/api/projects/restore",
        files={"file": (name, content, "application/zip")},
    )


def test_backup_download_contains_the_local_project_state(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "Restored chapter")
    upload_pages(client, project_id, ["page-1.png"])

    directory = Path(
        client.get(f"/api/projects/{project_id}").json()["directory"]
    )
    # A previous archive inside the project must not be nested in the new one.
    (directory / "backups" / "old.zip").write_bytes(b"not a backup")

    content, _disposition = _backup(client, project_id)

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {"manifest.json", "backup.json", "project.db"}.issubset(names)
        assert any(name.startswith("source/") for name in names)
        assert any(name.startswith("thumbnails/") for name in names)
        assert not any(name.startswith("backups/") for name in names)

        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["project_id"] == project_id
        assert manifest["name"] == "Quantum Mechanics"
        metadata = json.loads(archive.read("backup.json"))
        assert metadata["backup_version"] == 1
        assert metadata["project_id"] == project_id
        assert metadata["project_name"] == "Quantum Mechanics"


def test_restore_creates_a_new_project_and_keeps_the_original(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "Restored chapter")
    pages = upload_pages(client, project_id, ["page-1.png"])
    content, _disposition = _backup(client, project_id)

    response = _restore(client, content)
    assert response.status_code == 201, response.text
    restored = response.json()

    assert restored["id"] != project_id
    assert restored["name"] == "Quantum Mechanics (restored)"
    assert restored["page_count"] == 1
    assert restored["description"] == "Reference book"
    restored_directory = Path(restored["directory"])
    assert restored_directory.is_dir()
    assert (restored_directory / "manifest.json").is_file()
    assert (restored_directory / "project.db").is_file()
    assert json.loads((restored_directory / "manifest.json").read_text("utf-8"))[
        "project_id"
    ] == restored["id"]
    assert not (restored_directory / "backup.json").exists()

    document = client.get(f"/api/projects/{restored['id']}/document").json()
    assert document["plain_text"] == "Restored chapter"

    restored_pages = client.get(f"/api/projects/{restored['id']}/pages").json()
    assert [page["page_number"] for page in restored_pages] == [1]
    original = client.get(
        f"/api/projects/{restored['id']}/assets/"
        f"{restored_pages[0]['original_asset_id']}/file"
    )
    assert original.status_code == 200
    assert original.headers["content-type"].startswith("image/")
    assert len(original.content) > 0

    # The source project is untouched.
    assert client.get(f"/api/projects/{project_id}").status_code == 200
    assert (
        client.get(f"/api/projects/{project_id}/pages").json()[0]["id"]
        == pages[0]["id"]
    )


def test_restore_after_deletion_reuses_the_project_name(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "Survives deletion")
    content, _disposition = _backup(client, project_id)

    assert client.delete(f"/api/projects/{project_id}").status_code == 200

    response = _restore(client, content)
    assert response.status_code == 201, response.text
    restored = response.json()
    assert restored["name"] == "Quantum Mechanics"
    assert restored["id"] != project_id
    assert (
        client.get(f"/api/projects/{restored['id']}/document").json()["plain_text"]
        == "Survives deletion"
    )
    assert [item["id"] for item in client.get("/api/projects").json()] == [
        restored["id"]
    ]


def test_restore_rejects_unsafe_archive_paths(
    client: TestClient, project: dict
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("backup.json", "{}")
        archive.writestr("project.db", b"x")
        archive.writestr("../escaped.txt", b"no")

    response = _restore(client, buffer.getvalue())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_unsafe_path"


def test_restore_rejects_missing_or_invalid_files(
    client: TestClient, project: dict
) -> None:
    missing = io.BytesIO()
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("manifest.json", "{}")

    response = _restore(client, missing.getvalue())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_missing_files"

    broken_database = io.BytesIO()
    with zipfile.ZipFile(broken_database, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"schema_version": 1, "name": "Broken project"}),
        )
        archive.writestr("backup.json", json.dumps({"backup_version": 1}))
        archive.writestr("project.db", b"this is not a database")

    response = _restore(client, broken_database.getvalue())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_database_invalid"

    response = _restore(client, b"not a zip archive")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_invalid"


def test_restore_requires_a_zip_file(client: TestClient) -> None:
    response = _restore(client, b"anything", name="backup.tar")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_invalid"


def test_backup_capability_is_advertised(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert meta["capabilities"]["backup"] is True
    assert meta["max_backup_mb"] == 2048
