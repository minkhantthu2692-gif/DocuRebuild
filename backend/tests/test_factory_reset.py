from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import upload_pages


def test_factory_reset_requires_the_exact_confirmation(client: TestClient) -> None:
    response = client.post("/api/system/reset", json={"confirm": "delete"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "reset_confirmation_required"


def test_factory_reset_removes_projects_settings_keys_and_backups(
    client: TestClient, project: dict, tmp_path: Path
) -> None:
    project_id = project["id"]
    upload_pages(client, project_id, ["page.png"])
    client.patch("/api/settings", json={"language": "my"})

    data_dir = tmp_path / "data"
    (data_dir / "secrets").mkdir(parents=True, exist_ok=True)
    (data_dir / "secrets" / "ai_keys.enc").write_bytes(b"encrypted")
    (data_dir / "backups" / project_id).mkdir(parents=True, exist_ok=True)
    (data_dir / "backups" / project_id / "copy.zip").write_bytes(b"backup")
    (data_dir / "trash" / "old-project").mkdir(parents=True, exist_ok=True)
    (data_dir / "tmp" / "preview.png").write_bytes(b"preview")
    # A file the application does not own must survive a reset.
    (data_dir / "unrelated.txt").write_text("keep me", encoding="utf-8")

    response = client.post("/api/system/reset", json={"confirm": "DELETE"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["ok"] is True
    assert result["projects_removed"] == 1

    assert client.get("/api/projects").json() == []
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    assert health.json()["projects"] == 0
    assert client.get("/api/settings").json()["language"] == "en"

    assert (data_dir / "app.db").exists()
    assert (data_dir / "projects").is_dir()
    assert list((data_dir / "projects").iterdir()) == []
    assert not (data_dir / "secrets").exists()
    assert not (data_dir / "backups" / project_id).exists()
    assert not (data_dir / "trash" / "old-project").exists()
    assert not (data_dir / "tmp" / "preview.png").exists()
    assert (data_dir / "unrelated.txt").read_text(encoding="utf-8") == "keep me"


def test_factory_reset_can_run_twice(client: TestClient) -> None:
    first = client.post("/api/system/reset", json={"confirm": "DELETE"})
    assert first.status_code == 200
    second = client.post("/api/system/reset", json={"confirm": "DELETE"})
    assert second.status_code == 200
    assert second.json()["projects_removed"] == 0
    assert client.get("/api/health").json()["projects"] == 0
