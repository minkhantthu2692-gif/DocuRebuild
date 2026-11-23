from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_project_lifecycle(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    assert project["name"] == "Quantum Mechanics"
    assert project["page_count"] == 0
    assert project["document_updated_at"] is not None

    listing = client.get("/api/projects").json()
    assert [item["id"] for item in listing] == [project_id]

    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["description"] == "Reference book"

    directory = Path(detail["directory"])
    assert (directory / "manifest.json").exists()
    assert (directory / "project.db").exists()
    assert (directory / "source").is_dir()


def test_project_rename_and_open(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    renamed = client.patch(
        f"/api/projects/{project_id}", json={"name": "  Quantum   Mechanics 2 "}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Quantum Mechanics 2"

    opened = client.post(f"/api/projects/{project_id}/open")
    assert opened.status_code == 200
    assert opened.json()["last_opened_at"] is not None


def test_project_deletion_moves_folder_to_trash(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    directory = Path(client.get(f"/api/projects/{project_id}").json()["directory"])

    response = client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 200
    trash_path = Path(response.json()["trash_path"])
    assert trash_path.exists()
    assert not directory.exists()
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get("/api/projects").json() == []


def test_invalid_project_id_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/projects/not-a-uuid")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "project_not_found"


def test_document_round_trip(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    document = client.get(f"/api/projects/{project_id}/document").json()
    assert document["content"]["type"] == "doc"

    content = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Quantum Mechanics"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "The Schrödinger equation."}],
            },
        ],
    }
    saved = client.put(
        f"/api/projects/{project_id}/document",
        json={"content": content, "plain_text": "Quantum Mechanics\nThe Schrödinger equation."},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["updated_at"] is not None

    reloaded = client.get(f"/api/projects/{project_id}/document").json()
    assert reloaded["content"] == content
    assert "Schrödinger" in reloaded["plain_text"]


def test_document_rejects_non_document_payload(client: TestClient, project: dict) -> None:
    response = client.put(
        f"/api/projects/{project['id']}/document",
        json={"content": {"type": "paragraph"}, "plain_text": ""},
    )
    assert response.status_code == 422


def test_bulk_delete_moves_each_project_to_trash(client: TestClient) -> None:
    ids = [
        client.post("/api/projects", json={"name": f"Project {index}"}).json()["id"]
        for index in range(3)
    ]

    response = client.post(
        "/api/projects/bulk-delete",
        json={"project_ids": [ids[0], ids[1], ids[1], "not-a-project"]},
    )
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["deleted"] == [ids[0], ids[1]]
    assert result["failed"] == [
        {
            "id": "not-a-project",
            "code": "project_not_found",
            "message": "Project not found.",
        }
    ]
    assert len(result["trash_paths"]) == 2
    for trash_path in result["trash_paths"]:
        assert Path(trash_path).is_dir()

    remaining = client.get("/api/projects").json()
    assert [item["id"] for item in remaining] == [ids[2]]


def test_bulk_delete_never_moves_a_folder_outside_the_data_dir(
    client: TestClient, project: dict, tmp_path: Path
) -> None:
    """A copied or stale database must not delete another location's folder."""
    import sqlite3

    from app.core.config import get_settings

    outside = tmp_path / "outside-storage"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")

    database = sqlite3.connect(get_settings().database_path)
    database.execute(
        "UPDATE projects SET directory = ? WHERE id = ?", (str(outside), project["id"])
    )
    database.commit()
    database.close()

    response = client.post(
        "/api/projects/bulk-delete", json={"project_ids": [project["id"]]}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["deleted"] == []
    assert result["failed"][0]["code"] == "project_storage_outside_data_dir"

    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert client.get(f"/api/projects/{project['id']}").status_code == 200


def test_bulk_delete_requires_at_least_one_project(client: TestClient) -> None:
    response = client.post("/api/projects/bulk-delete", json={"project_ids": []})
    assert response.status_code == 422


def test_bulk_delete_reports_a_missing_project_without_stopping(
    client: TestClient, project: dict
) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    response = client.post(
        "/api/projects/bulk-delete",
        json={"project_ids": [missing, project["id"]]},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["deleted"] == [project["id"]]
    assert result["failed"][0]["id"] == missing
    assert client.get("/api/projects").json() == []
