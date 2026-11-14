from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
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


def _page_row(directory: str, page_id: str) -> dict:
    with project_db(Path(directory)) as conn:
        row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    assert row is not None
    return dict(row)


def _asset_row(directory: str, asset_id: str) -> dict | None:
    with project_db(Path(directory)) as conn:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return dict(row) if row is not None else None


def _remove_asset_file(directory: str, asset_id: str) -> None:
    asset = _asset_row(directory, asset_id)
    assert asset is not None
    path = Path(directory) / asset["relative_path"]
    assert path.is_file()
    path.unlink()


def _drop_page_asset(directory: str, page_id: str, column: str) -> None:
    with project_db(Path(directory)) as conn:
        page = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        asset_id = page[column]
        conn.execute(f"UPDATE pages SET {column} = NULL WHERE id = ?", (page_id,))
        conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))


def _add_ocr_run(directory: str, page_id: str, source_asset_id: str) -> None:
    with project_db(Path(directory)) as conn:
        conn.execute(
            "INSERT INTO ocr_runs (id, page_id, status, engine, languages,"
            " source_asset_id, rotation, text, created_at, updated_at, completed_at)"
            " VALUES ('run-repair', ?, 'completed', 'tesseract', 'eng', ?, 0,"
            " 'Repair text', '2026-01-01T00:00:00+00:00',"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            (page_id, source_asset_id),
        )


def _repair(
    client: TestClient, project_id: str, token: str, page_id: str
):
    return client.post(
        f"/api/projects/{project_id}/backup/selection/{token}/page-assets",
        json={"page_id": page_id},
    )


def test_repair_page_image_in_place_keeps_ocr_and_elements(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["page.png"])[0]
    before = _page_row(project["directory"], page["id"])
    original_id = before["original_asset_id"]
    assert original_id is not None
    _add_ocr_run(project["directory"], page["id"], original_id)
    element = client.post(
        f"/api/projects/{project_id}/pages/{page['id']}/elements",
        json={
            "kind": "figure",
            "x": 10,
            "y": 20,
            "width": 100,
            "height": 80,
            "caption": "Kept crop",
        },
    )
    assert element.status_code == 201, element.text
    element_id = element.json()["id"]

    filename = _make_copy(client, project_id)
    _remove_asset_file(project["directory"], original_id)

    selection = _inspect_copy(client, project_id, filename)
    summary = selection["pages"][0]
    assert summary["in_project"] is True
    assert summary["missing_slots"] == ["original"]
    assert summary["restorable_slots"] == ["original"]

    response = _repair(client, project_id, selection["token"], page["id"])
    assert response.status_code == 200, response.text
    assert response.json() == {
        "page_id": page["id"],
        "page_number": 1,
        "restored_slots": ["original"],
    }

    after = _page_row(project["directory"], page["id"])
    # The existing asset row is reused, so references stay valid.
    assert after["original_asset_id"] == original_id
    asset = _asset_row(project["directory"], original_id)
    assert asset is not None
    assert (Path(project["directory"]) / asset["relative_path"]).stat().st_size > 0

    ocr = client.get(f"/api/projects/{project_id}/pages/{page['id']}/ocr").json()
    assert ocr["id"] == "run-repair"
    assert ocr["source_asset_id"] == original_id
    assert ocr["stale"] is False

    elements = client.get(
        f"/api/projects/{project_id}/pages/{page['id']}/elements"
    ).json()
    assert [item["id"] for item in elements] == [element_id]

    # The inspection token survives a repair, so several pages can be fixed.
    again = _repair(client, project_id, selection["token"], page["id"])
    assert again.status_code == 200, again.text
    assert again.json()["restored_slots"] == []


def test_repair_page_image_uses_a_new_asset_when_the_row_is_gone(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["page.png"])[0]
    before = _page_row(project["directory"], page["id"])
    original_id = before["original_asset_id"]

    filename = _make_copy(client, project_id)
    _drop_page_asset(project["directory"], page["id"], "original_asset_id")

    selection = _inspect_copy(client, project_id, filename)
    summary = selection["pages"][0]
    assert summary["missing_slots"] == ["original"]
    assert summary["restorable_slots"] == ["original"]

    response = _repair(client, project_id, selection["token"], page["id"])
    assert response.status_code == 200, response.text
    assert response.json()["restored_slots"] == ["original"]

    after = _page_row(project["directory"], page["id"])
    assert after["original_asset_id"] is not None
    assert after["original_asset_id"] != original_id
    assert _asset_row(project["directory"], after["original_asset_id"]) is not None


def test_repair_leaves_present_images_alone(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["page.png"])[0]
    before = _page_row(project["directory"], page["id"])
    filename = _make_copy(client, project_id)

    selection = _inspect_copy(client, project_id, filename)
    summary = selection["pages"][0]
    assert summary["missing_slots"] == []
    assert summary["restorable_slots"] == []

    response = _repair(client, project_id, selection["token"], page["id"])
    assert response.status_code == 200, response.text
    assert response.json()["restored_slots"] == []

    after = _page_row(project["directory"], page["id"])
    for column in ("original_asset_id", "display_asset_id", "thumbnail_asset_id"):
        assert after[column] == before[column]


def test_repair_rejects_a_page_that_is_not_in_the_project(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["page.png"])[0]
    filename = _make_copy(client, project_id)
    with project_db(Path(project["directory"])) as conn:
        conn.execute("DELETE FROM pages WHERE id = ?", (page["id"],))

    selection = _inspect_copy(client, project_id, filename)
    summary = selection["pages"][0]
    assert summary["in_project"] is False
    assert summary["missing_slots"] == []
    assert summary["restorable_slots"] == []

    response = _repair(client, project_id, selection["token"], page["id"])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "page_not_in_project"


def test_repair_refuses_a_corrupt_backup_image(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["page.png"])[0]
    before = _page_row(project["directory"], page["id"])
    original_id = before["original_asset_id"]

    filename = _make_copy(client, project_id)
    _remove_asset_file(project["directory"], original_id)
    selection = _inspect_copy(client, project_id, filename)

    staging = get_settings().tmp_dir / f"select-{selection['token']}"
    with sqlite3.connect(staging / "project.db") as conn:
        row = conn.execute(
            "SELECT relative_path FROM assets WHERE id = ?", (original_id,)
        ).fetchone()
    assert row is not None
    (staging / row[0]).write_bytes(b"not the original image")

    response = _repair(client, project_id, selection["token"], page["id"])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backup_checksum_mismatch"


def test_repair_reports_when_the_backup_file_is_missing(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["page.png"])[0]
    before = _page_row(project["directory"], page["id"])
    original_id = before["original_asset_id"]

    filename = _make_copy(client, project_id)
    _remove_asset_file(project["directory"], original_id)
    selection = _inspect_copy(client, project_id, filename)

    staging = get_settings().tmp_dir / f"select-{selection['token']}"
    with sqlite3.connect(staging / "project.db") as conn:
        row = conn.execute(
            "SELECT relative_path FROM assets WHERE id = ?", (original_id,)
        ).fetchone()
    assert row is not None
    (staging / row[0]).unlink()

    response = _repair(client, project_id, selection["token"], page["id"])
    assert response.status_code == 200, response.text
    assert response.json()["restored_slots"] == []
