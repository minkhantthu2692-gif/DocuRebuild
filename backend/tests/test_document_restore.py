from __future__ import annotations

from fastapi.testclient import TestClient


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


def _checkpoint(client: TestClient, project_id: str) -> dict:
    response = client.post(f"/api/projects/{project_id}/document/revisions")
    assert response.status_code == 201, response.text
    return response.json()


def _make_copy(client: TestClient, project_id: str) -> str:
    response = client.post(f"/api/projects/{project_id}/backups")
    assert response.status_code == 201, response.text
    return response.json()["filename"]


def _inspect_copy(client: TestClient, project_id: str, filename: str) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/backups/{filename}/selection"
    )
    assert response.status_code == 200, response.text
    return response.json()


def _restore_document(
    client: TestClient,
    project_id: str,
    token: str,
    revision_id: str | None = None,
):
    return client.post(
        f"/api/projects/{project_id}/backup/selection/{token}/document",
        json={"revision_id": revision_id},
    )


def _live_text(client: TestClient, project_id: str) -> str:
    response = client.get(f"/api/projects/{project_id}/document")
    assert response.status_code == 200, response.text
    return response.json()["plain_text"]


def test_inspect_lists_the_current_document_and_its_revisions(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "First draft")
    checkpoint = _checkpoint(client, project_id)
    _save_document(client, project_id, "Second draft")

    filename = _make_copy(client, project_id)
    selection = _inspect_copy(client, project_id, filename)

    document = selection["document"]
    assert document["current"]["preview"] == "Second draft"
    assert document["current"]["character_count"] == len("Second draft")
    assert document["current"]["updated_at"]
    assert [revision["id"] for revision in document["revisions"]] == [
        checkpoint["id"]
    ]
    assert document["revisions"][0]["source"] == "manual"
    assert document["revisions"][0]["preview"] == "First draft"


def test_restore_one_document_revision_from_a_stored_copy(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "Original text")
    checkpoint = _checkpoint(client, project_id)
    _save_document(client, project_id, "Current live text")

    filename = _make_copy(client, project_id)
    # Edit after the copy was made, so the restore has something to replace.
    _save_document(client, project_id, "Changed after backup")

    selection = _inspect_copy(client, project_id, filename)
    revision = next(
        item
        for item in selection["document"]["revisions"]
        if item["id"] == checkpoint["id"]
    )
    assert revision["preview"] == "Original text"

    response = _restore_document(
        client, project_id, selection["token"], revision["id"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["restored"] is True
    assert body["source"] == "revision"
    assert body["revision_id"] == revision["id"]
    assert body["document"]["plain_text"] == "Original text"
    assert body["document"]["content"]["type"] == "doc"
    assert _live_text(client, project_id) == "Original text"

    # The replaced state is now in the local history, so the restore is reversible.
    revisions = client.get(
        f"/api/projects/{project_id}/document/revisions"
    ).json()
    assert revisions[0]["preview"] == "Changed after backup"

    events = client.get(f"/api/projects/{project_id}/history").json()
    restored = next(
        event for event in events if event["event_type"] == "document_restored"
    )
    assert restored["payload"]["document_source"] == "revision"
    assert restored["payload"]["character_count"] == len("Original text")
    assert "Original text" not in str(restored)


def test_restore_the_current_document_from_a_copy(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "Backup current text")
    filename = _make_copy(client, project_id)
    _save_document(client, project_id, "Newer live text")

    selection = _inspect_copy(client, project_id, filename)
    assert selection["document"]["current"]["preview"] == "Backup current text"

    response = _restore_document(client, project_id, selection["token"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "current"
    assert body["revision_id"] is None
    assert _live_text(client, project_id) == "Backup current text"

    revisions = client.get(
        f"/api/projects/{project_id}/document/revisions"
    ).json()
    assert revisions[0]["preview"] == "Newer live text"


def test_a_backup_without_pages_can_still_restore_its_document(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "Text only")
    filename = _make_copy(client, project_id)
    _save_document(client, project_id, "After the copy")

    selection = _inspect_copy(client, project_id, filename)
    assert selection["pages"] == []
    assert selection["document"]["current"]["preview"] == "Text only"

    response = _restore_document(client, project_id, selection["token"])
    assert response.status_code == 200, response.text
    assert _live_text(client, project_id) == "Text only"


def test_unknown_document_revision_is_rejected(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "Keep this text")
    filename = _make_copy(client, project_id)
    selection = _inspect_copy(client, project_id, filename)

    response = _restore_document(
        client, project_id, selection["token"], "missing-revision"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_document_missing"
    assert _live_text(client, project_id) == "Keep this text"
