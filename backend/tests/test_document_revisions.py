from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.services import documents


def _doc(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _save(client: TestClient, project_id: str, text: str) -> None:
    response = client.put(
        f"/api/projects/{project_id}/document",
        json={"content": _doc(text), "plain_text": text},
    )
    assert response.status_code == 200, response.text


def _revisions(client: TestClient, project_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/projects/{project_id}/document/revisions")
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_initial_state_is_not_a_version(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    client.get(f"/api/projects/{project_id}/document")

    _save(client, project_id, "First draft")

    assert _revisions(client, project_id) == []


def test_changed_save_snapshots_the_previous_state(
    client: TestClient, project: dict, monkeypatch
) -> None:
    project_id = project["id"]
    _save(client, project_id, "First draft")
    monkeypatch.setattr(documents, "REVISION_INTERVAL_SECONDS", 0)
    _save(client, project_id, "Second draft")

    revisions = _revisions(client, project_id)
    assert len(revisions) == 1
    assert revisions[0]["source"] == "autosave"
    assert revisions[0]["preview"] == "First draft"
    assert revisions[0]["character_count"] == len("First draft")

    detail = client.get(
        f"/api/projects/{project_id}/document/revisions/{revisions[0]['id']}"
    ).json()
    assert detail["content"] == _doc("First draft")
    assert detail["plain_text"] == "First draft"


def test_unchanged_save_does_not_duplicate_revisions(
    client: TestClient, project: dict, monkeypatch
) -> None:
    project_id = project["id"]
    _save(client, project_id, "Only once")
    monkeypatch.setattr(documents, "REVISION_INTERVAL_SECONDS", 0)
    _save(client, project_id, "Only once")

    assert _revisions(client, project_id) == []


def test_automatic_snapshots_are_coalesced(
    client: TestClient, project: dict, monkeypatch
) -> None:
    project_id = project["id"]
    _save(client, project_id, "One")
    _save(client, project_id, "Two")

    # The first meaningful change is kept immediately; later edits inside the
    # interval are not versioned individually.
    assert [revision["preview"] for revision in _revisions(client, project_id)] == ["One"]

    _save(client, project_id, "Three")
    assert [revision["preview"] for revision in _revisions(client, project_id)] == ["One"]

    # Once the interval has passed, the next change keeps the state it replaces.
    monkeypatch.setattr(documents, "REVISION_INTERVAL_SECONDS", 0)
    _save(client, project_id, "Four")

    revisions = _revisions(client, project_id)
    assert [revision["preview"] for revision in revisions] == ["Three", "One"]


def test_manual_checkpoint_and_deduplication(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save(client, project_id, "Checkpoint")

    created = client.post(f"/api/projects/{project_id}/document/revisions")
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "manual"
    assert created.json()["preview"] == "Checkpoint"

    again = client.post(f"/api/projects/{project_id}/document/revisions")
    assert again.status_code == 201, again.text
    assert again.json()["id"] == created.json()["id"]
    revisions = _revisions(client, project_id)
    assert len(revisions) == 1
    assert revisions[0]["preview"] == "Checkpoint"


def test_restore_replaces_the_document_and_keeps_the_replaced_state(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save(client, project_id, "Current")
    checkpoint = client.post(f"/api/projects/{project_id}/document/revisions").json()
    _save(client, project_id, "Edited")

    response = client.post(
        f"/api/projects/{project_id}/document/revisions/{checkpoint['id']}/restore"
    )
    assert response.status_code == 200, response.text
    assert response.json()["content"] == _doc("Current")
    assert response.json()["plain_text"] == "Current"

    document = client.get(f"/api/projects/{project_id}/document").json()
    assert document["content"] == _doc("Current")

    revisions = _revisions(client, project_id)
    # The edited state is kept even though the coalescing interval has not passed.
    assert revisions[0]["preview"] == "Edited"
    assert revisions[0]["character_count"] == len("Edited")
    assert "Current" in [revision["preview"] for revision in revisions]

    # A restore is itself reversible from the same history.
    back = client.post(
        f"/api/projects/{project_id}/document/revisions/{revisions[0]['id']}/restore"
    )
    assert back.status_code == 200, back.text
    assert client.get(f"/api/projects/{project_id}/document").json()["content"] == _doc(
        "Edited"
    )


def test_restore_preserves_the_exact_document_model(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    original = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2, "textAlign": "center"},
                "content": [{"type": "text", "text": "Chapter"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Bold", "marks": [{"type": "bold"}]},
                    {
                        "type": "text",
                        "text": " link",
                        "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                    },
                ],
            },
            {"type": "figure", "attrs": {"caption": "Figure 1", "src": "/api/asset"}},
        ],
    }
    client.put(
        f"/api/projects/{project_id}/document",
        json={"content": original, "plain_text": "Chapter\n\nBold link\n\nFigure 1"},
    )
    checkpoint = client.post(f"/api/projects/{project_id}/document/revisions").json()
    _save(client, project_id, "Something else")

    restored = client.post(
        f"/api/projects/{project_id}/document/revisions/{checkpoint['id']}/restore"
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["content"] == original
    assert restored.json()["plain_text"] == "Chapter\n\nBold link\n\nFigure 1"


def test_revision_limit_is_validated(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    for value in ("0", "201", "many"):
        response = client.get(
            f"/api/projects/{project_id}/document/revisions", params={"limit": value}
        )
        assert response.status_code == 422, value


def test_old_revisions_are_pruned(
    client: TestClient, project: dict, monkeypatch
) -> None:
    monkeypatch.setattr(documents, "REVISION_LIMIT", 3)
    project_id = project["id"]

    for index in range(5):
        _save(client, project_id, f"version {index}")
        created = client.post(f"/api/projects/{project_id}/document/revisions")
        assert created.status_code == 201, created.text

    revisions = _revisions(client, project_id)
    assert len(revisions) == 3
    assert [revision["preview"] for revision in revisions] == [
        "version 4",
        "version 3",
        "version 2",
    ]


def test_unknown_revision_returns_not_found(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    response = client.get(
        f"/api/projects/{project_id}/document/revisions/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "revision_not_found"

    restore = client.post(
        f"/api/projects/{project_id}/document/revisions/00000000-0000-0000-0000-000000000000/restore"
    )
    assert restore.status_code == 404


def test_revisions_for_unknown_project_return_not_found(client: TestClient) -> None:
    response = client.get(
        "/api/projects/00000000-0000-0000-0000-000000000000/document/revisions"
    )
    assert response.status_code == 404
