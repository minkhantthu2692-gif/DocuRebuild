from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import AppError
from app.services import local_backups


def test_vault_starts_empty(client: TestClient, project: dict) -> None:
    response = client.get(f"/api/projects/{project['id']}/backups")
    assert response.status_code == 200
    assert response.json() == []


def test_backup_copy_can_be_created_listed_and_downloaded(
    client: TestClient, project: dict
) -> None:
    created = client.post(f"/api/projects/{project['id']}/backups")
    assert created.status_code == 201, created.text
    copy = created.json()
    assert copy["filename"].endswith(".zip")
    assert copy["byte_size"] > 0
    assert copy["created_at"]

    listing = client.get(f"/api/projects/{project['id']}/backups")
    assert listing.status_code == 200
    assert listing.json() == [copy]

    download = client.get(
        f"/api/projects/{project['id']}/backups/{quote(copy['filename'])}"
    )
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert download.content[:2] == b"PK"
    assert "no-store" in download.headers["cache-control"]

    # Downloading a copy never removes it from the vault.
    again = client.get(f"/api/projects/{project['id']}/backups")
    assert again.json() == [copy]


def test_vault_keeps_only_the_newest_copies(client: TestClient, project: dict) -> None:
    saved = client.patch("/api/settings", json={"backups": {"keep_copies": 2}})
    assert saved.status_code == 200, saved.text
    names = []
    for _ in range(3):
        response = client.post(f"/api/projects/{project['id']}/backups")
        assert response.status_code == 201, response.text
        names.append(response.json()["filename"])

    # Same-second copies get distinct names instead of overwriting each other.
    assert len(set(names)) == 3
    listing = client.get(f"/api/projects/{project['id']}/backups").json()
    assert len(listing) == 2
    kept = {entry["filename"] for entry in listing}
    assert kept.issubset(set(names))
    assert kept == set(names[-2:])
    folder = local_backups.vault_dir(project["id"])
    assert len(list(folder.glob("*.zip"))) == 2


def test_unknown_backup_copy_is_not_found(client: TestClient, project: dict) -> None:
    response = client.get(f"/api/projects/{project['id']}/backups/missing.zip")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "backup_not_found"


def test_non_archive_names_are_rejected(project: dict) -> None:
    for name in ("project.db", "backup.tar", "", "../outside.zip", "sub/inside.zip"):
        with pytest.raises(AppError) as exc:
            local_backups.resolve_copy(project["id"], name)
        assert exc.value.status_code == 404


def test_due_check_uses_the_newest_copy(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    assert local_backups.is_due(project_id, 24)

    created = client.post(f"/api/projects/{project_id}/backups")
    assert created.status_code == 201, created.text

    assert not local_backups.is_due(project_id, 24)
    later = datetime.now(timezone.utc) + timedelta(hours=25)
    assert local_backups.is_due(project_id, 24, now=later)


def test_manual_copies_respect_the_saved_retention(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    saved = client.patch("/api/settings", json={"backups": {"keep_copies": 2}})
    assert saved.status_code == 200, saved.text

    for _ in range(3):
        response = client.post(f"/api/projects/{project_id}/backups")
        assert response.status_code == 201, response.text

    listing = client.get(f"/api/projects/{project_id}/backups").json()
    assert len(listing) == 2


def test_opening_a_project_creates_a_due_automatic_copy(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    saved = client.patch(
        "/api/settings",
        json={"backups": {"auto_on_open": True, "interval_hours": 24}},
    )
    assert saved.status_code == 200, saved.text

    opened = client.post(f"/api/projects/{project_id}/open")
    assert opened.status_code == 200, opened.text

    listing = client.get(f"/api/projects/{project_id}/backups").json()
    assert len(listing) == 1

    # A second open inside the interval must not create another copy.
    again = client.post(f"/api/projects/{project_id}/open")
    assert again.status_code == 200, again.text
    assert len(client.get(f"/api/projects/{project_id}/backups").json()) == 1


def test_automatic_copies_stay_off_by_default(client: TestClient, project: dict) -> None:
    assert client.post(f"/api/projects/{project['id']}/open").status_code == 200
    assert client.get(f"/api/projects/{project['id']}/backups").json() == []


def test_one_copy_can_be_deleted_explicitly(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    created = client.post(f"/api/projects/{project_id}/backups")
    assert created.status_code == 201, created.text
    filename = created.json()["filename"]

    deleted = client.delete(f"/api/projects/{project_id}/backups/{quote(filename)}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"ok": True, "filename": filename}
    assert client.get(f"/api/projects/{project_id}/backups").json() == []

    again = client.delete(f"/api/projects/{project_id}/backups/{quote(filename)}")
    assert again.status_code == 404
    assert again.json()["detail"]["code"] == "backup_not_found"


def test_deleting_a_project_moves_its_vault_to_trash(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    assert client.post(f"/api/projects/{project_id}/backups").status_code == 201
    vault = local_backups.vault_dir(project_id)
    assert list(vault.glob("*.zip"))

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 200, deleted.text
    assert not vault.exists()

    moved = list(get_settings().trash_dir.glob("*-vault"))
    assert len(moved) == 1
    assert list(moved[0].glob("*.zip"))


def test_a_stored_copy_restores_as_a_new_project(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    created = client.post(f"/api/projects/{project_id}/backups")
    assert created.status_code == 201, created.text
    filename = created.json()["filename"]

    restored = client.post(
        f"/api/projects/{project_id}/backups/{quote(filename)}/restore"
    )
    assert restored.status_code == 201, restored.text
    body = restored.json()
    assert body["id"] != project_id
    assert body["name"] == "Quantum Mechanics (restored)"

    # Restoring is additive: the original project and the copy are untouched.
    assert client.get(f"/api/projects/{project_id}").status_code == 200
    assert len(client.get(f"/api/projects/{project_id}/backups").json()) == 1
    assert local_backups.vault_dir(project_id).joinpath(filename).is_file()
    assert client.get(f"/api/projects/{body['id']}").status_code == 200


def test_restoring_a_missing_copy_fails_cleanly(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    missing = client.post(f"/api/projects/{project_id}/backups/missing.zip/restore")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "backup_not_found"
