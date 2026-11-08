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
