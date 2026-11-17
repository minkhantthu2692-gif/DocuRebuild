from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.services import document_layout


def test_layout_defaults_are_empty_and_hide_no_page_numbers(
    client: TestClient, project: dict
) -> None:
    response = client.get(f"/api/projects/{project['id']}/document/layout")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["header_text"] == ""
    assert body["footer_text"] == ""
    assert body["show_page_numbers"] is True
    assert body["updated_at"]


def test_layout_round_trip_normalizes_whitespace(client: TestClient, project: dict) -> None:
    saved = client.put(
        f"/api/projects/{project['id']}/document/layout",
        json={
            "header_text": "  Chapter\n1   Running  head ",
            "footer_text": "\tDraft footer\t",
            "show_page_numbers": False,
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["header_text"] == "Chapter 1 Running head"
    assert body["footer_text"] == "Draft footer"
    assert body["show_page_numbers"] is False

    replayed = client.get(f"/api/projects/{project['id']}/document/layout").json()
    assert replayed["header_text"] == "Chapter 1 Running head"
    assert replayed["footer_text"] == "Draft footer"
    assert replayed["show_page_numbers"] is False


def test_layout_rejects_overlong_text(client: TestClient, project: dict) -> None:
    response = client.put(
        f"/api/projects/{project['id']}/document/layout",
        json={"header_text": "x" * 201, "footer_text": "", "show_page_numbers": True},
    )
    assert response.status_code == 422


def test_layout_history_records_state_without_the_text(
    client: TestClient, project: dict
) -> None:
    client.put(
        f"/api/projects/{project['id']}/document/layout",
        json={
            "header_text": "Private running head",
            "footer_text": "Private footer",
            "show_page_numbers": True,
        },
    )
    events = client.get(f"/api/projects/{project['id']}/history").json()
    event = next(
        item for item in events if item["event_type"] == "document_layout_updated"
    )
    assert event["payload"] == {
        "has_header": True,
        "has_footer": True,
        "show_page_numbers": True,
    }
    assert "Private" not in json.dumps(event)


def test_layout_is_stored_in_the_project_database(tmp_path: Path) -> None:
    document_layout.write_layout(
        tmp_path,
        header_text="Head",
        footer_text="Foot",
        show_page_numbers=False,
    )
    stored = document_layout.read_layout(tmp_path)
    assert stored["header_text"] == "Head"
    assert stored["footer_text"] == "Foot"
    assert stored["show_page_numbers"] is False

    # Reading again never resets a saved layout.
    assert document_layout.read_layout(tmp_path) == stored
