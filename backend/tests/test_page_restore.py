from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db.project_schema import project_db
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


def _add_ocr_and_suggestion(directory: str, page_id: str) -> tuple[str, str]:
    """Insert an OCR run, a verified block and a pending AI suggestion."""
    run_id = "run-from-backup"
    block_id = "block-from-backup"
    with project_db(Path(directory)) as conn:
        conn.execute(
            "INSERT INTO ocr_runs (id, page_id, status, engine, languages, text,"
            " created_at, updated_at, completed_at) VALUES (?, ?, 'completed',"
            " 'tesseract', 'eng', 'Chapter one', '2026-01-01T00:00:00+00:00',"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            (run_id, page_id),
        )
        conn.execute(
            "INSERT INTO ocr_blocks (id, run_id, page_id, block_index, kind, text,"
            " confidence, x, y, width, height, line_count, word_count, verified,"
            " corrected, created_at, updated_at) VALUES (?, ?, ?, 0, 'paragraph',"
            " 'Chapter one text', 91.5, 10, 20, 300, 40, 1, 3, 1, 0,"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            (block_id, run_id, page_id),
        )
        conn.execute(
            "INSERT INTO ai_suggestions (id, page_id, block_id, task, original_text,"
            " proposed_text, provider, model, base_url, status, created_at, updated_at)"
            " VALUES ('suggestion-1', ?, ?, 'ocr_cleanup', 'Chapter one text',"
            " 'Chapter One Text', 'ollama', 'llama3', 'http://127.0.0.1:11434',"
            " 'pending', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            (page_id, block_id),
        )
    return run_id, block_id


def _make_copy(client: TestClient, project_id: str) -> str:
    response = client.post(f"/api/projects/{project_id}/backups")
    assert response.status_code == 201, response.text
    return response.json()["filename"]


def _inspect_copy(
    client: TestClient, project_id: str, filename: str
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/backups/{filename}/selection"
    )
    assert response.status_code == 200, response.text
    return response.json()


def _inspect_upload(
    client: TestClient,
    project_id: str,
    content: bytes,
    *,
    name: str = "backup.zip",
    password: str | None = None,
) -> dict:
    data = {"password": password} if password is not None else None
    response = client.post(
        f"/api/projects/{project_id}/backup/selection",
        files={"file": (name, content, "application/octet-stream")},
        data=data,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _apply(
    client: TestClient, project_id: str, token: str, page_ids: list[str]
):
    return client.post(
        f"/api/projects/{project_id}/backup/selection/{token}/pages",
        json={"page_ids": page_ids},
    )


def test_restore_one_page_from_a_stored_copy(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    _save_document(client, project_id, "The live document")
    pages = upload_pages(client, project_id, ["page-1.png", "page-2.png"])
    first, second = pages
    _add_ocr_and_suggestion(project["directory"], first["id"])

    element = client.post(
        f"/api/projects/{project_id}/pages/{first['id']}/elements",
        json={
            "kind": "figure",
            "x": 10,
            "y": 20,
            "width": 100,
            "height": 80,
            "caption": "Restored crop",
        },
    )
    assert element.status_code == 201, element.text
    element_body = element.json()

    filename = _make_copy(client, project_id)
    selection = _inspect_copy(client, project_id, filename)
    assert [page["id"] for page in selection["pages"]] == [first["id"], second["id"]]
    assert selection["source_name"] == filename

    response = _apply(client, project_id, selection["token"], [first["id"]])
    assert response.status_code == 200, response.text
    assert response.json() == {"restored": 1, "page_numbers": [3]}

    listed = client.get(f"/api/projects/{project_id}/pages").json()
    assert [page["page_number"] for page in listed] == [1, 2, 3]
    # The original pages are untouched.
    assert listed[0]["id"] == first["id"]
    assert listed[1]["id"] == second["id"]

    restored = listed[2]
    assert restored["id"] != first["id"]
    assert restored["original_filename"] == "page-1.png"

    ocr = client.get(
        f"/api/projects/{project_id}/pages/{restored['id']}/ocr"
    ).json()
    assert ocr["text"] == "Chapter one"
    assert ocr["blocks"][0]["text"] == "Chapter one text"
    assert ocr["blocks"][0]["verified"] is True
    assert ocr["blocks"][0]["confidence"] == 91.5

    suggestions = client.get(
        f"/api/projects/{project_id}/pages/{restored['id']}/ai-suggestions"
    )
    assert suggestions.status_code == 200, suggestions.text
    assert [item["proposed_text"] for item in suggestions.json()["suggestions"]] == [
        "Chapter One Text"
    ]

    elements = client.get(
        f"/api/projects/{project_id}/pages/{restored['id']}/elements"
    ).json()
    assert len(elements) == 1
    assert elements[0]["caption"] == "Restored crop"
    assert elements[0]["id"] != element_body["id"]
    assert elements[0]["asset_id"] != element_body["asset_id"]
    assert elements[0]["stale"] is False
    asset = client.get(
        f"/api/projects/{project_id}/assets/{elements[0]['asset_id']}/file"
    )
    assert asset.status_code == 200, asset.text

    # Copying a page never changes the document text.
    document = client.get(f"/api/projects/{project_id}/document").json()
    assert document["plain_text"] == "The live document"

    # The staging extraction is removed and the token cannot be reused.
    assert _apply(client, project_id, selection["token"], [first["id"]]).status_code == 410


def test_restore_pages_from_an_uploaded_archive(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    pages = upload_pages(client, project_id, ["a.png", "b.png", "c.png"])
    backup = client.get(f"/api/projects/{project_id}/backup")
    assert backup.status_code == 200

    selection = _inspect_upload(client, project_id, backup.content)
    assert len(selection["pages"]) == 3

    chosen = [selection["pages"][0]["id"], selection["pages"][2]["id"]]
    response = _apply(client, project_id, selection["token"], chosen)
    assert response.status_code == 200, response.text
    assert response.json() == {"restored": 2, "page_numbers": [4, 5]}

    listed = client.get(f"/api/projects/{project_id}/pages").json()
    assert [page["page_number"] for page in listed] == [1, 2, 3, 4, 5]
    assert listed[3]["original_filename"] == "a.png"
    assert listed[4]["original_filename"] == "c.png"
    assert [page["id"] for page in listed[:3]] == [page["id"] for page in pages]


def test_encrypted_upload_needs_its_password_to_inspect(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    upload_pages(client, project_id, ["page.png"])
    encrypted = client.post(
        f"/api/projects/{project_id}/backup", json={"password": PASSWORD}
    )
    assert encrypted.status_code == 200

    missing = client.post(
        f"/api/projects/{project_id}/backup/selection",
        files={"file": ("book.drbz", encrypted.content, "application/octet-stream")},
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "backup_password_required"

    selection = _inspect_upload(
        client,
        project_id,
        encrypted.content,
        name="book.drbz",
        password=PASSWORD,
    )
    assert len(selection["pages"]) == 1


def test_selection_belongs_to_the_project_that_inspected_it(
    client: TestClient, project: dict
) -> None:
    other = client.post(
        "/api/projects", json={"name": "Another book", "description": ""}
    )
    assert other.status_code == 201, other.text
    other_id = other.json()["id"]
    upload_pages(client, project["id"], ["page.png"])
    filename = _make_copy(client, project["id"])
    selection = _inspect_copy(client, project["id"], filename)

    response = _apply(client, other_id, selection["token"], [selection["pages"][0]["id"]])
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "restore_selection_expired"

    # The project that inspected it can still apply the selection.
    ok = _apply(
        client, project["id"], selection["token"], [selection["pages"][0]["id"]]
    )
    assert ok.status_code == 200, ok.text


def test_selection_rejects_empty_or_unknown_pages(
    client: TestClient, project: dict
) -> None:
    upload_pages(client, project["id"], ["page.png"])
    filename = _make_copy(client, project["id"])
    selection = _inspect_copy(client, project["id"], filename)

    empty = _apply(client, project["id"], selection["token"], [])
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "page_selection_empty"

    unknown = _apply(
        client, project["id"], selection["token"], ["00000000-0000-0000-0000-000000000000"]
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "page_selection_invalid"


def test_unknown_selection_token_expires(client: TestClient, project: dict) -> None:
    response = _apply(client, project["id"], "f" * 32, ["page"])
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "restore_selection_expired"

    malformed = _apply(client, project["id"], "g" * 32, ["page"])
    assert malformed.status_code == 410
