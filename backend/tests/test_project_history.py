from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import upload_pages


def _history(client: TestClient, project_id: str, limit: int = 100) -> list[dict]:
    response = client.get(
        f"/api/projects/{project_id}/history", params={"limit": limit}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_history_returns_local_events_newest_first(client: TestClient, project: dict) -> None:
    upload_pages(client, project["id"], ["activity-page.png"])
    saved = client.put(
        f"/api/projects/{project['id']}/document",
        json={
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Activity export"}],
                    }
                ],
            },
            "plain_text": "Activity export",
        },
    )
    assert saved.status_code == 200, saved.text
    export = client.get(f"/api/projects/{project['id']}/document/export?format=txt")
    assert export.status_code == 200

    events = _history(client, project["id"])
    types = [event["event_type"] for event in events]
    assert types[0] == "document_exported"
    assert "pages_imported" in types
    assert "project_created" in types

    imported = next(event for event in events if event["event_type"] == "pages_imported")
    assert imported["payload"]["count"] == 1
    assert imported["payload"]["cancelled"] is False

    exported = events[0]
    assert exported["payload"]["format"] == "txt"
    assert exported["payload"]["byte_size"] > 0

    timestamps = [event["created_at"] for event in events]
    assert timestamps == sorted(timestamps, reverse=True)


def test_history_never_contains_document_text(client: TestClient, project: dict) -> None:
    secret = "TOP-SECRET-ACTIVITY-TEXT"
    saved = client.put(
        f"/api/projects/{project['id']}/document",
        json={
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": secret}],
                    }
                ],
            },
            "plain_text": secret,
        },
    )
    assert saved.status_code == 200, saved.text
    assert client.get(f"/api/projects/{project['id']}/document/export").status_code == 200

    payload = _history(client, project["id"])
    serialized = str(payload)
    assert secret not in serialized
    exported = payload[0]
    assert exported["event_type"] == "document_exported"
    assert set(exported["payload"]) == {"format", "byte_size"}


def test_history_limit_is_bounded(client: TestClient, project: dict) -> None:
    upload_pages(client, project["id"], ["limit-page.png"])

    first = _history(client, project["id"], limit=1)
    assert len(first) == 1
    assert first[0]["event_type"] == "pages_imported"

    assert (
        client.get(
            f"/api/projects/{project['id']}/history", params={"limit": 0}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/projects/{project['id']}/history", params={"limit": 201}
        ).status_code
        == 422
    )


def test_history_is_scoped_to_one_project(client: TestClient, project: dict) -> None:
    other = client.post("/api/projects", json={"name": "Other project"})
    assert other.status_code == 201, other.text

    events = _history(client, other.json()["id"])
    assert [event["event_type"] for event in events] == ["project_created"]


def test_history_reports_a_missing_project(client: TestClient) -> None:
    response = client.get("/api/projects/missing-project/history")
    assert response.status_code == 404
