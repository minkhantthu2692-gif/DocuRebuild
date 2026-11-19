"""Workflow-level AI tests: review, staleness, bulk decisions and vision.

The provider, rotation and credential tests live in ``test_ai_byok``. This
module reuses its local stub server and connection helpers so every workflow
runs through the same BYOK task router.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import upload_pages
from tests.test_ai_byok import (  # noqa: F401 - fixture imported for pytest
    _configure,
    _create_connection,
    _ocr_page,
    _test,
    stub_ai,
)


def _suggest(
    client: TestClient,
    project_id: str,
    page_id: str,
    block_id: str,
    payload: dict | None = None,
):
    return client.post(
        f"/api/projects/{project_id}/pages/{page_id}/ocr/blocks/{block_id}/ai-suggestions",
        json=payload or {},
    )


def _usage(client: TestClient) -> dict:
    response = client.get("/api/ai/usage")
    assert response.status_code == 200, response.text
    return response.json()


def _configured_text(client: TestClient, stub_ai) -> dict:
    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    _configure(client, connection, task="ocr_cleanup", model_id="text-large")
    return connection


def _configured_vision(client: TestClient, stub_ai) -> dict:
    connection = _create_connection(client, base_url=stub_ai.base_url_v1)
    _test(client, connection)
    _configure(client, connection, task="region_proposals", model_id="vision-large")
    _configure(
        client, connection, task="equation_transcription", model_id="vision-large"
    )
    _configure(client, connection, task="table_structure", model_id="vision-large")
    return connection


def test_cleanup_requires_a_configured_model(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _ocr_page(client, project, monkeypatch, "ai-unconfigured.png")
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ai_task_not_configured"
    assert _usage(client)["used"] == 0


def test_cleanup_records_usage_and_enforces_rolling_limit(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configured_text(client, stub_ai)
    page, run = _ocr_page(client, project, monkeypatch, "ai-usage.png")
    empty = _usage(client)
    assert empty["used"] == 0
    assert empty["recent"] == []
    assert empty["by_task"] == []
    assert empty["remaining"] is None

    created = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert created.status_code == 201, created.text
    after_success = _usage(client)
    assert after_success["used"] == 1
    assert after_success["successful"] == 1
    assert after_success["by_task"] == [{"task": "ocr_cleanup", "used": 1}]
    entry = after_success["recent"][0]
    assert entry["outcome"] == "success"
    assert entry["connection_name"] == "Test provider"
    assert entry["model"] == "text-large"
    assert entry["task"] == "ocr_cleanup"
    assert entry["project_id"] == project["id"]
    assert entry["page_id"] == page["id"]
    assert entry["block_id"] == run["blocks"][0]["id"]
    assert entry["input_tokens"] == 10
    assert entry["output_tokens"] == 20

    # A provider request that fails still counts, because it used the server.
    stub_ai.state.failures["key-a"] = ("always", 503)
    failed = _suggest(client, project["id"], page["id"], run["blocks"][1]["id"])
    assert failed.status_code == 502, failed.text
    assert failed.json()["detail"]["code"] == "ai_provider_unavailable"
    after_failure = _usage(client)
    assert after_failure["used"] == 2
    assert after_failure["successful"] == 1
    assert after_failure["failed"] == 1
    assert after_failure["recent"][0]["outcome"] == "error"
    assert after_failure["recent"][0]["error_code"] == "ai_provider_unavailable"
    stub_ai.state.failures.pop("key-a", None)

    limited = client.patch("/api/ai/preferences", json={"daily_request_limit": 2})
    assert limited.status_code == 200, limited.text
    blocked = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["detail"]["code"] == "ai_request_limit_reached"
    after_block = _usage(client)
    assert after_block["used"] == 2
    assert after_block["request_limit"] == 2
    assert after_block["remaining"] == 0

    raised = client.patch("/api/ai/preferences", json={"daily_request_limit": 3})
    assert raised.status_code == 200
    allowed = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert allowed.status_code == 201, allowed.text
    assert _usage(client)["used"] == 3


def test_page_suggestions_can_be_listed_and_filtered(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    stub_ai.state.chat_reply = "Chapter One (cleaned)"
    _configured_text(client, stub_ai)
    page_a, run_a = _ocr_page(client, project, monkeypatch, "ai-list-a.png")
    page_b, run_b = _ocr_page(client, project, monkeypatch, "ai-list-b.png")

    first = _suggest(
        client, project["id"], page_a["id"], run_a["blocks"][0]["id"]
    ).json()["suggestion"]
    second = _suggest(
        client, project["id"], page_a["id"], run_a["blocks"][1]["id"]
    ).json()["suggestion"]
    third = _suggest(
        client, project["id"], page_b["id"], run_b["blocks"][0]["id"]
    ).json()["suggestion"]
    decided = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{first['id']}",
        json={"status": "accepted"},
    )
    assert decided.status_code == 200, decided.text

    all_a = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions"
    )
    assert all_a.status_code == 200, all_a.text
    assert {item["id"] for item in all_a.json()["suggestions"]} == {
        first["id"],
        second["id"],
    }

    accepted = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"status": "accepted"},
    ).json()["suggestions"]
    assert [item["id"] for item in accepted] == [first["id"]]
    assert accepted[0]["original_text"] == "Chapter One"
    assert accepted[0]["proposed_text"] == "Chapter One (cleaned)"

    pending = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"status": "pending"},
    ).json()["suggestions"]
    assert [item["id"] for item in pending] == [second["id"]]

    other_page = client.get(
        f"/api/projects/{project['id']}/pages/{page_b['id']}/ai-suggestions"
    ).json()["suggestions"]
    assert [item["id"] for item in other_page] == [third["id"]]

    limited = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"limit": 1},
    ).json()["suggestions"]
    assert [item["id"] for item in limited] == [second["id"]]

    for bad_limit in (0, 501):
        response = client.get(
            f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
            params={"limit": bad_limit},
        )
        assert response.status_code == 422, bad_limit

    invalid = client.get(
        f"/api/projects/{project['id']}/pages/{page_a['id']}/ai-suggestions",
        params={"status": "unknown"},
    )
    assert invalid.status_code == 422

    missing = client.get(
        f"/api/projects/{project['id']}/pages/unknown-page/ai-suggestions"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "page_not_found"

    project_all = client.get(
        f"/api/projects/{project['id']}/ai-suggestions"
    ).json()["suggestions"]
    assert {item["id"] for item in project_all} == {
        first["id"],
        second["id"],
        third["id"],
    }
    by_id = {item["id"]: item for item in project_all}
    assert by_id[first["id"]]["page_number"] == page_a["page_number"]
    assert by_id[third["id"]]["page_number"] == page_b["page_number"]

    project_pending = client.get(
        f"/api/projects/{project['id']}/ai-suggestions",
        params={"status": "pending"},
    ).json()["suggestions"]
    assert {item["id"] for item in project_pending} == {second["id"], third["id"]}


def test_cleanup_suggestion_is_reviewable_and_accepting_updates_text(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    stub_ai.state.chat_reply = "Chapter One (cleaned)"
    _configured_text(client, stub_ai)
    page, run = _ocr_page(client, project, monkeypatch, "ai-cleanup.png")
    block = run["blocks"][0]

    created = _suggest(client, project["id"], page["id"], block["id"])
    assert created.status_code == 201, created.text
    body = created.json()
    suggestion = body["suggestion"]
    assert suggestion["status"] == "pending"
    assert suggestion["task"] == "ocr_cleanup"
    assert suggestion["original_text"] == "Chapter One"
    assert suggestion["proposed_text"] == "Chapter One (cleaned)"
    assert suggestion["provider"] == "openai_compatible"
    assert suggestion["model"] == "text-large"
    assert suggestion["base_url"] == stub_ai.base_url_v1
    assert body["run"]["blocks"][0]["text"] == "Chapter One"

    accepted = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    decided = accepted.json()
    assert decided["suggestion"]["status"] == "accepted"
    assert decided["run"]["blocks"][0]["text"] == "Chapter One (cleaned)"
    assert decided["run"]["blocks"][0]["corrected"] is True


def test_cleanup_rejects_when_ocr_text_changed_after_proposal(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    stub_ai.state.chat_reply = "Chapter One (cleaned)"
    _configured_text(client, stub_ai)
    page, run = _ocr_page(client, project, monkeypatch, "ai-stale-text.png")
    block = run["blocks"][0]
    suggestion = _suggest(
        client, project["id"], page["id"], block["id"]
    ).json()["suggestion"]

    edited = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr/blocks/{block['id']}",
        json={"text": "Chapter One (manual)"},
    )
    assert edited.status_code == 200

    accepted = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 409
    assert accepted.json()["detail"]["code"] == "ai_suggestion_stale"

    rejected = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["suggestion"]["status"] == "rejected"
    assert rejected.json()["run"]["blocks"][0]["text"] == "Chapter One (manual)"


def test_cleanup_refuses_a_stale_ocr_run(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configured_text(client, stub_ai)
    page, run = _ocr_page(client, project, monkeypatch, "ai-stale-run.png")
    rotated = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/rotate",
        json={"degrees": 90},
    )
    assert rotated.status_code == 200
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_stale"


def test_cleanup_empty_response_is_not_stored(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    _configured_text(client, stub_ai)
    page, run = _ocr_page(client, project, monkeypatch, "ai-empty.png")
    stub_ai.state.chat_reply = "   "
    response = _suggest(client, project["id"], page["id"], run["blocks"][0]["id"])
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ai_empty_response"


def test_rejected_suggestion_keeps_text_and_cannot_be_redecided(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    stub_ai.state.chat_reply = "Chapter One (cleaned)"
    _configured_text(client, stub_ai)
    page, run = _ocr_page(client, project, monkeypatch, "ai-reject.png")
    block = run["blocks"][0]
    suggestion = _suggest(
        client, project["id"], page["id"], block["id"]
    ).json()["suggestion"]

    rejected = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["run"]["blocks"][0]["text"] == "Chapter One"

    again = client.patch(
        f"/api/projects/{project['id']}/ai-suggestions/{suggestion['id']}",
        json={"status": "accepted"},
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "ai_suggestion_not_pending"


def test_bulk_reject_reviews_every_unique_pending_proposal(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    stub_ai.state.chat_reply = "Chapter One (cleaned)"
    _configured_text(client, stub_ai)
    page, run = _ocr_page(client, project, monkeypatch, "ai-bulk-reject.png")
    first = _suggest(
        client, project["id"], page["id"], run["blocks"][0]["id"]
    ).json()["suggestion"]
    second = _suggest(
        client, project["id"], page["id"], run["blocks"][1]["id"]
    ).json()["suggestion"]

    response = client.post(
        f"/api/projects/{project['id']}/ai-suggestions/bulk",
        json={"ids": [first["id"], second["id"], first["id"]], "status": "rejected"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requested"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    assert [item["id"] for item in body["results"]] == [first["id"], second["id"]]
    assert [item["status"] for item in body["results"]] == ["rejected", "rejected"]

    latest = client.get(f"/api/projects/{project['id']}/pages/{page['id']}/ocr").json()
    assert [block["text"] for block in latest["blocks"]] == [
        "Chapter One",
        "A local OCR result.",
    ]


def test_bulk_accept_skips_stale_proposals_and_reports_each_item(
    client: TestClient, project: dict, monkeypatch, stub_ai
) -> None:
    stub_ai.state.chat_reply = "Chapter One (cleaned)"
    _configured_text(client, stub_ai)
    page, run = _ocr_page(client, project, monkeypatch, "ai-bulk-accept.png")
    stale_block = run["blocks"][0]
    fresh_block = run["blocks"][1]
    stale = _suggest(
        client, project["id"], page["id"], stale_block["id"]
    ).json()["suggestion"]
    fresh = _suggest(
        client, project["id"], page["id"], fresh_block["id"]
    ).json()["suggestion"]

    edited = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr/blocks/{stale_block['id']}",
        json={"text": "Manual correction"},
    )
    assert edited.status_code == 200, edited.text

    response = client.post(
        f"/api/projects/{project['id']}/ai-suggestions/bulk",
        json={"ids": [stale["id"], fresh["id"]], "status": "accepted"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requested"] == 2
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    assert body["results"][0] == {
        "id": stale["id"],
        "status": None,
        "error_code": "ai_suggestion_stale",
    }
    assert body["results"][1] == {
        "id": fresh["id"],
        "status": "accepted",
        "error_code": None,
    }

    latest = client.get(f"/api/projects/{project['id']}/pages/{page['id']}/ocr").json()
    assert latest["blocks"][0]["text"] == "Manual correction"
    assert latest["blocks"][1]["text"] == "Chapter One (cleaned)"

    missing = client.post(
        f"/api/projects/{project['id']}/ai-suggestions/bulk",
        json={"ids": ["missing-id"], "status": "rejected"},
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["failed"] == 1
    assert missing.json()["results"][0]["error_code"] == "ai_suggestion_not_found"


def _vision(
    client: TestClient, project_id: str, page_id: str, payload: dict | None = None
):
    return client.post(
        f"/api/projects/{project_id}/pages/{page_id}/ai-region-proposals",
        json=payload or {},
    )


def test_vision_region_proposals_map_coordinates_and_record_usage(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    page = upload_pages(client, project["id"], ["ai-vision.png"])[0]
    response = _vision(client, project["id"], page["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["page_width"] == 1200
    assert body["page_height"] == 800
    assert body["provider"] == "openai_compatible"
    assert body["model"] == "vision-large"

    proposal = body["proposals"][0]
    assert proposal["kind"] == "figure"
    assert proposal["reason"] == "ai_vision"
    assert proposal["confidence"] == "low"
    assert proposal["caption"] == "Figure 1"
    assert (proposal["x"], proposal["y"]) == (110, 154)
    assert (proposal["width"], proposal["height"]) == (380, 332)

    payload = stub_ai.state.last_payload
    assert payload is not None
    content = payload["messages"][-1]["content"]
    assert isinstance(content, list)
    image = next(item for item in content if item["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")

    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["task"] == "region_proposals"
    assert usage["recent"][0]["page_id"] == page["id"]
    assert usage["recent"][0]["block_id"] is None


def test_vision_region_proposals_drop_unusable_regions(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    page = upload_pages(client, project["id"], ["ai-vision-filter.png"])[0]
    stub_ai.state.vision_reply = json.dumps(
        {
            "regions": [
                {
                    "kind": "paragraph",
                    "x": 0.1,
                    "y": 0.1,
                    "width": 0.2,
                    "height": 0.2,
                },
                {"kind": "table", "x": -0.2, "y": 0.1, "width": 0.2, "height": 0.2},
                {"kind": "figure", "x": 0.9, "y": 0.1, "width": 0.5, "height": 0.2},
                {
                    "kind": "equation",
                    "x": 0.4,
                    "y": 0.4,
                    "width": 0.2,
                    "height": 0.1,
                },
            ]
        }
    )
    response = _vision(client, project["id"], page["id"])
    assert response.status_code == 200, response.text
    proposals = response.json()["proposals"]
    assert [item["kind"] for item in proposals] == ["figure", "equation"]
    assert all(item["caption"] == "" for item in proposals)
    figure = proposals[0]
    assert figure["x"] + figure["width"] <= 1200


def test_vision_region_proposals_report_invalid_output(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    page = upload_pages(client, project["id"], ["ai-vision-invalid.png"])[0]
    stub_ai.state.vision_reply = "I could not analyse the image."
    response = _vision(client, project["id"], page["id"])
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "ai_invalid_response"
    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["outcome"] == "error"
    assert usage["recent"][0]["error_code"] == "ai_invalid_response"
    assert usage["recent"][0]["task"] == "region_proposals"


def _region(
    client: TestClient, project_id: str, page_id: str, kind: str = "equation"
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/pages/{page_id}/elements",
        json={
            "kind": kind,
            "x": 100,
            "y": 120,
            "width": 300,
            "height": 120,
            "caption": "",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _equation(
    client: TestClient, project_id: str, element_id: str, payload: dict | None = None
):
    return client.post(
        f"/api/projects/{project_id}/elements/{element_id}/ai-equation",
        json=payload or {},
    )


def test_equation_transcription_returns_a_reviewable_proposal(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    stub_ai.state.vision_reply = "E = mc^{2}"
    page = upload_pages(client, project["id"], ["ai-equation.png"])[0]
    element = _region(client, project["id"], page["id"])

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["latex"] == "E = mc^{2}"
    assert body["provider"] == "openai_compatible"
    assert body["model"] == "vision-large"
    assert body["element_id"] == element["id"]
    assert body["page_id"] == page["id"]

    payload = stub_ai.state.last_payload
    assert payload is not None
    assert payload["model"] == "vision-large"
    content = payload["messages"][-1]["content"]
    image = next(item for item in content if item["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")

    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    )
    assert listed.json()[0]["text"] == ""

    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["task"] == "equation_transcription"
    assert usage["recent"][0]["page_id"] == page["id"]


def test_equation_transcription_strips_model_wrappers(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    stub_ai.state.vision_reply = "```latex\n$$\nE = mc^2\n$$\n```"
    page = upload_pages(client, project["id"], ["ai-equation-wrapper.png"])[0]
    element = _region(client, project["id"], page["id"])

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 200, response.text
    assert response.json()["latex"] == "E = mc^2"


def test_equation_transcription_refuses_other_region_kinds(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    page = upload_pages(client, project["id"], ["ai-equation-figure.png"])[0]
    element = _region(client, project["id"], page["id"], kind="figure")

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ai_equation_region_required"
    assert _usage(client)["used"] == 0


def test_equation_transcription_reports_an_empty_reply(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    stub_ai.state.vision_reply = "   "
    page = upload_pages(client, project["id"], ["ai-equation-empty.png"])[0]
    element = _region(client, project["id"], page["id"])

    response = _equation(client, project["id"], element["id"])
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "ai_equation_empty"
    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["outcome"] == "error"
    assert usage["recent"][0]["error_code"] == "ai_equation_empty"


def test_equation_latex_parser_strips_only_wrappers() -> None:
    from app.services.ai import parse_equation_latex

    assert parse_equation_latex("```\n$$x^{2}$$\n```") == "x^{2}"
    assert parse_equation_latex('"\\[ a + b \\]"') == "a + b"
    assert parse_equation_latex("  E = mc^2  ") == "E = mc^2"


def test_table_grid_parser_accepts_only_a_complete_rectangle() -> None:
    from app.core.errors import AppError
    from app.services.ai import parse_table_grid

    assert parse_table_grid('{"rows": [["Item", "Qty"], ["Apples", "3"]]}') == [
        ["Item", "Qty"],
        ["Apples", "3"],
    ]
    assert parse_table_grid('```json\n{"rows": [["1", "2"], ["3", 4]]}\n```') == [
        ["1", "2"],
        ["3", "4"],
    ]
    assert parse_table_grid('{"rows": [["a", null], ["c", "d"]]}') == [
        ["a", ""],
        ["c", "d"],
    ]

    for reply in (
        "not json",
        '{"rows": []}',
        '{"rows": [["a", "b"], ["c"]]}',
        '{"rows": [["a"], ["b"]]}',
        '{"rows": [["a", ["b"]], ["c", "d"]]}',
        '{"rows": [["a", true], ["c", "d"]]}',
    ):
        with pytest.raises(AppError) as excinfo:
            parse_table_grid(reply)
        assert excinfo.value.status_code == 502

    too_many_rows = json.dumps({"rows": [["a", "b"]] * 61})
    with pytest.raises(AppError) as excinfo:
        parse_table_grid(too_many_rows)
    assert excinfo.value.code == "ai_table_too_large"


def _table(
    client: TestClient, project_id: str, element_id: str, payload: dict | None = None
):
    return client.post(
        f"/api/projects/{project_id}/elements/{element_id}/ai-table",
        json=payload or {},
    )


def test_ai_table_returns_a_reviewable_grid(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    stub_ai.state.vision_reply = json.dumps(
        {"rows": [["Item", "Qty"], ["Apples", "3"], ["Pears", ""]]}
    )
    page = upload_pages(client, project["id"], ["ai-table.png"])[0]
    element = _region(client, project["id"], page["id"], kind="table")

    response = _table(client, project["id"], element["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["element_id"] == element["id"]
    assert body["page_id"] == page["id"]
    assert body["provider"] == "openai_compatible"
    assert body["model"] == "vision-large"
    assert body["rows"] == 3
    assert body["columns"] == 2
    assert body["page_width"] == 1200
    assert body["page_height"] == 800
    assert body["warnings"] == ["no_confidence"]
    assert body["cells"][0] == {
        "row": 0,
        "column": 0,
        "text": "Item",
        "confidence": None,
        "uncertain": False,
        "empty": False,
        "alignment": None,
        "rowspan": 1,
        "colspan": 1,
    }
    assert body["empty_cells"] == 1
    assert body["cells"][-1]["empty"] is True

    payload = stub_ai.state.last_payload
    assert payload is not None
    assert payload["model"] == "vision-large"

    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    )
    assert listed.json()[0]["text"] == ""

    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["task"] == "table_structure"
    assert usage["by_task"] == [{"task": "table_structure", "used": 1}]


def test_ai_table_refuses_an_incomplete_grid(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    stub_ai.state.vision_reply = json.dumps({"rows": [["Item", "Qty"], ["Apples"]]})
    page = upload_pages(client, project["id"], ["ai-table-ragged.png"])[0]
    element = _region(client, project["id"], page["id"], kind="table")

    response = _table(client, project["id"], element["id"])
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "ai_table_ragged"

    usage = _usage(client)
    assert usage["used"] == 1
    assert usage["recent"][0]["outcome"] == "error"
    assert usage["recent"][0]["error_code"] == "ai_table_ragged"


def _insert_usage(
    *,
    model: str,
    task: str,
    outcome: str,
    created_at,
    project_id: str | None,
    error_code: str | None = None,
) -> None:
    import uuid

    from app.db.models import AiUsage
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        session.add(
            AiUsage(
                id=str(uuid.uuid4()),
                provider="openai_compatible",
                model=model,
                task=task,
                outcome=outcome,
                error_code=error_code,
                project_id=project_id,
                page_id=None,
                block_id=None,
                created_at=created_at,
            )
        )
        session.commit()


def test_ai_usage_history_pages_filters_and_names_projects(
    client: TestClient, project: dict
) -> None:
    from datetime import datetime

    other = client.post(
        "/api/projects",
        json={"name": "Second Ledger Project", "description": ""},
    )
    assert other.status_code == 201, other.text
    other_id = other.json()["id"]

    _insert_usage(
        model="cleanup-model",
        task="ocr_cleanup",
        outcome="success",
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        project_id=project["id"],
    )
    _insert_usage(
        model="cleanup-model",
        task="ocr_cleanup",
        outcome="error",
        error_code="ai_timeout",
        created_at=datetime(2026, 1, 1, 11, 0, 0),
        project_id=project["id"],
    )
    _insert_usage(
        model="vision-model",
        task="region_proposals",
        outcome="success",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        project_id=other_id,
    )
    _insert_usage(
        model="detached-model",
        task="equation_transcription",
        outcome="success",
        created_at=datetime(2026, 1, 1, 13, 0, 0),
        project_id=None,
    )

    response = client.get("/api/ai/usage/history")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 4
    assert body["limit"] == 25
    assert body["offset"] == 0
    assert [entry["model"] for entry in body["entries"]] == [
        "detached-model",
        "vision-model",
        "cleanup-model",
        "cleanup-model",
    ]
    assert body["entries"][0]["project_name"] is None
    assert body["entries"][1]["project_name"] == "Second Ledger Project"
    assert body["entries"][2]["project_name"] == "Quantum Mechanics"
    assert body["entries"][2]["outcome"] == "error"
    assert body["entries"][2]["error_code"] == "ai_timeout"

    page = client.get("/api/ai/usage/history", params={"limit": 2, "offset": 1})
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 4
    assert [entry["model"] for entry in page.json()["entries"]] == [
        "vision-model",
        "cleanup-model",
    ]

    failed = client.get("/api/ai/usage/history", params={"outcome": "error"})
    assert failed.status_code == 200, failed.text
    assert failed.json()["total"] == 1
    assert failed.json()["entries"][0]["error_code"] == "ai_timeout"

    regions = client.get(
        "/api/ai/usage/history", params={"task": "region_proposals"}
    )
    assert regions.status_code == 200, regions.text
    assert regions.json()["total"] == 1
    assert regions.json()["entries"][0]["project_name"] == "Second Ledger Project"

    combined = client.get(
        "/api/ai/usage/history",
        params={"task": "ocr_cleanup", "outcome": "success"},
    )
    assert combined.status_code == 200, combined.text
    assert combined.json()["total"] == 1
    assert combined.json()["entries"][0]["project_name"] == "Quantum Mechanics"

    assert client.get("/api/ai/usage/history", params={"limit": 0}).status_code == 422
    assert (
        client.get("/api/ai/usage/history", params={"task": "unknown"}).status_code
        == 422
    )


def test_corrupt_key_store_degrades_to_no_key(client: TestClient) -> None:
    from app.core.config import get_settings

    secrets_dir = get_settings().data_dir / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "ai_keys.enc").write_bytes(b"not-a-fernet-token")

    # Listing connections must not fail just because the vault is unreadable.
    response = client.get("/api/ai/connections")
    assert response.status_code == 200, response.text

# ---------------------------------------------------------------------------
# Ledger ordering, project schema and remaining workflow guards.
# ---------------------------------------------------------------------------


def test_usage_breakdown_counts_tasks_in_a_stable_order(
    client: TestClient, project: dict
) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for task in ("equation_transcription", "ocr_cleanup", "ocr_cleanup"):
        _insert_usage(
            model="qwen2.5:7b",
            task=task,
            outcome="success",
            created_at=now,
            project_id=project["id"],
        )
    # A stored name this build does not know must still be counted and shown
    # instead of disappearing from the budget it consumed.
    _insert_usage(
        model="qwen2.5:7b",
        task="legacy_task",
        outcome="error",
        error_code="ai_unreachable",
        created_at=now,
        project_id=project["id"],
    )

    body = _usage(client)
    assert body["used"] == 4
    # Errors consume the budget, so the failed attempt is included.
    assert body["by_task"] == [
        {"task": "ocr_cleanup", "used": 2},
        {"task": "equation_transcription", "used": 1},
        {"task": "legacy_task", "used": 1},
    ]


def test_project_schema_contains_ai_suggestions(client: TestClient, project: dict) -> None:
    from pathlib import Path

    from app.db.project_schema import project_db

    with project_db(Path(project["directory"])) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert "ai_suggestions" in tables


def test_vision_region_proposals_require_a_configured_task(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["ai-vision-unconfigured.png"])[0]
    response = _vision(client, project["id"], page["id"])
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ai_task_not_configured"
    # Nothing was sent, so nothing is counted.
    assert _usage(client)["used"] == 0


def test_equation_transcription_rejects_an_unknown_region(
    client: TestClient, project: dict, stub_ai
) -> None:
    _configured_vision(client, stub_ai)
    missing = "00000000-0000-4000-8000-000000000000"
    response = _equation(client, project["id"], missing)
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "element_not_found"
    assert "/v1/chat/completions" not in stub_ai.state.paths
    assert _usage(client)["used"] == 0
