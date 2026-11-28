from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import upload_pages
from tests.test_regions import _block, _engine_available, _fake_result, _run_ocr

EQUATION_BLOCKS = [
    _block(1, "paragraph", "Intro text.", 100, 80, 500, 40),
    _block(2, "equation", "a^2 + b^2 = c^2", 100, 200, 320, 40),
    _block(3, "table", "A B", 100, 320, 500, 100),
    _block(4, "equation", "E = mc^2", 100, 500, 260, 40),
]


def _configure_ocr(monkeypatch, blocks: list[dict]) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr, "_perform_ocr", lambda *args, **kwargs: _fake_result(blocks)
    )


def _page_equations(
    client: TestClient, project_id: str, page_id: str
) -> dict:
    response = client.get(
        f"/api/projects/{project_id}/pages/{page_id}/equation-proposals"
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_page_equations_list_equation_blocks_in_reading_order(
    client: TestClient, project: dict, monkeypatch
) -> None:
    _configure_ocr(monkeypatch, EQUATION_BLOCKS)
    page = upload_pages(client, project["id"], ["equations.png"])[0]
    _run_ocr(client, project["id"], page["id"])

    body = _page_equations(client, project["id"], page["id"])
    assert body["status"] == "ready"
    assert body["page_id"] == page["id"]
    assert body["page_width"] == 1200
    assert body["page_height"] == 800
    assert body["engine"] == "tesseract"
    assert body["ocr_run_id"]

    proposals = body["proposals"]
    # The paragraph and the table are not equations, and the two equations are
    # ordered by their position on the page.
    assert [item["reading_index"] for item in proposals] == [0, 1]
    assert [item["text"] for item in proposals] == ["a^2 + b^2 = c^2", "E = mc^2"]
    assert proposals[0]["y"] < proposals[1]["y"]
    assert all(item["display"] is True for item in proposals)
    assert all(item["reason"] == "equation_text" for item in proposals)
    assert all(item["confidence"] == "high" for item in proposals)
    assert all(len(item["block_ids"]) == 1 for item in proposals)


def test_page_equations_merge_stacked_equation_blocks(
    client: TestClient, project: dict, monkeypatch
) -> None:
    _configure_ocr(
        monkeypatch,
        [
            _block(1, "equation", "x = 1", 100, 200, 300, 40),
            _block(2, "equation", "+ y = 2", 100, 244, 300, 40),
        ],
    )
    page = upload_pages(client, project["id"], ["equations-stacked.png"])[0]
    _run_ocr(client, project["id"], page["id"])

    body = _page_equations(client, project["id"], page["id"])
    assert body["status"] == "ready"
    assert len(body["proposals"]) == 1
    proposal = body["proposals"][0]
    assert proposal["reading_index"] == 0
    assert proposal["text"] == "x = 1 + y = 2"
    assert len(proposal["block_ids"]) == 2


def test_page_equations_need_an_ocr_run(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["equations-none.png"])[0]

    body = _page_equations(client, project["id"], page["id"])
    assert body["status"] == "no_ocr_run"
    assert body["proposals"] == []
    assert body["ocr_run_id"] is None
    assert body["page_width"] == 1200
    assert body["page_height"] == 800


def test_page_equations_skip_saved_elements(
    client: TestClient, project: dict, monkeypatch
) -> None:
    _configure_ocr(monkeypatch, EQUATION_BLOCKS)
    page = upload_pages(client, project["id"], ["equations-saved.png"])[0]
    _run_ocr(client, project["id"], page["id"])

    created = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements",
        json={
            "kind": "equation",
            "x": 100,
            "y": 200,
            "width": 320,
            "height": 40,
            "caption": "Already extracted",
        },
    )
    assert created.status_code == 201, created.text

    body = _page_equations(client, project["id"], page["id"])
    assert [item["text"] for item in body["proposals"]] == ["E = mc^2"]
    assert [item["reading_index"] for item in body["proposals"]] == [0]
