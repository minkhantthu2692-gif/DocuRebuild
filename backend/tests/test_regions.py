from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.conftest import upload_pages


def _engine_available() -> dict:
    return {
        "engine": "tesseract",
        "available": True,
        "version": "5.3.3",
        "command": "tesseract",
        "tessdata_dir": None,
        "languages": ["eng"],
        "preferred_languages": ["eng"],
        "reason": None,
        "setup_hint": None,
    }


def _block(index: int, kind: str, text: str, x, y, width, height) -> dict:
    return {
        "block_index": index,
        "kind": kind,
        "text": text,
        "confidence": 90.0,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "line_count": 1,
        "word_count": max(1, len(text.split())),
    }


def _fake_result(blocks: list[dict]) -> dict:
    return {
        "engine_version": "5.3.3",
        "text": "\n\n".join(block["text"] for block in blocks),
        "mean_confidence": 90.0,
        "blocks": blocks,
    }


def _run_ocr(client: TestClient, project_id: str, page_id: str) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/pages/{page_id}/ocr",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 202, response.text
    deadline = time.monotonic() + 5.0
    latest = None
    while time.monotonic() < deadline:
        latest = client.get(
            f"/api/projects/{project_id}/pages/{page_id}/ocr"
        ).json()
        if latest and latest["status"] in {"succeeded", "failed"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"OCR run did not finish: {latest}")


LAYOUT_BLOCKS = [
    _block(1, "table", "A B C", 100, 100, 500, 120),
    _block(2, "equation", "x = y + 1", 100, 300, 300, 40),
    _block(3, "paragraph", "Body text.", 100, 420, 500, 80),
    _block(4, "caption", "Figure 2. Layout", 100, 600, 300, 30),
]


def test_region_proposals_use_the_latest_ocr_layout(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr, "_perform_ocr", lambda *args, **kwargs: _fake_result(LAYOUT_BLOCKS)
    )

    page = upload_pages(client, project["id"], ["proposal-page.png"])[0]
    _run_ocr(client, project["id"], page["id"])

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["page_width"] == 1200
    assert body["page_height"] == 800
    assert body["engine"] == "tesseract"
    assert body["ocr_run_id"]

    by_kind = {proposal["kind"]: proposal for proposal in body["proposals"]}
    assert set(by_kind) == {"figure", "table", "equation"}

    table = by_kind["table"]
    assert table["reason"] == "table_text_grid"
    assert table["confidence"] == "high"
    assert table["x"] <= 100 and table["y"] <= 100
    assert table["x"] + table["width"] >= 600
    assert table["y"] + table["height"] >= 220
    assert len(table["block_ids"]) == 1

    equation = by_kind["equation"]
    assert equation["reason"] == "equation_text"
    assert equation["y"] <= 300 < equation["y"] + equation["height"]

    figure = by_kind["figure"]
    assert figure["reason"] == "figure_caption_gap"
    assert figure["confidence"] == "medium"
    assert figure["caption"] == "Figure 2. Layout"
    # The suggestion covers the empty band between the last text and the caption.
    assert figure["y"] >= 490
    assert figure["y"] + figure["height"] <= 610
    assert figure["width"] >= 500

    for proposal in body["proposals"]:
        assert proposal["x"] >= 0 and proposal["y"] >= 0
        assert proposal["x"] + proposal["width"] <= 1200
        assert proposal["y"] + proposal["height"] <= 800


def test_region_proposals_require_ocr(client: TestClient, project: dict) -> None:
    page = upload_pages(client, project["id"], ["proposal-no-ocr.png"])[0]
    body = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    ).json()
    assert body["status"] == "no_ocr_run"
    assert body["ocr_run_id"] is None
    assert body["proposals"] == []


def test_region_proposals_report_a_stale_ocr_run(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr, "_perform_ocr", lambda *args, **kwargs: _fake_result(LAYOUT_BLOCKS)
    )
    page = upload_pages(client, project["id"], ["proposal-stale.png"])[0]
    _run_ocr(client, project["id"], page["id"])

    rotated = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/rotate",
        json={"degrees": 90},
    )
    assert rotated.status_code == 200, rotated.text

    body = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    ).json()
    assert body["status"] == "ocr_stale"
    assert body["proposals"] == []


def test_region_proposals_skip_regions_already_extracted(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr, "_perform_ocr", lambda *args, **kwargs: _fake_result(LAYOUT_BLOCKS)
    )
    page = upload_pages(client, project["id"], ["proposal-existing.png"])[0]
    _run_ocr(client, project["id"], page["id"])

    created = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements",
        json={
            "kind": "table",
            "x": 100,
            "y": 100,
            "width": 500,
            "height": 120,
            "caption": "Already extracted",
        },
    )
    assert created.status_code == 201, created.text

    body = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    ).json()
    kinds = {proposal["kind"] for proposal in body["proposals"]}
    assert "table" not in kinds
    assert "figure" in kinds


def test_region_proposals_report_missing_block_geometry(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr,
        "_perform_ocr",
        lambda *args, **kwargs: _fake_result(
            [_block(1, "table", "A B", None, None, None, None)]
        ),
    )
    page = upload_pages(client, project["id"], ["proposal-no-geometry.png"])[0]
    _run_ocr(client, project["id"], page["id"])

    body = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    ).json()
    assert body["status"] == "no_geometry"
    assert body["proposals"] == []


def test_region_proposals_report_a_failed_ocr_run(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.core.errors import AppError
    from app.services import ocr

    def fail(*args, **kwargs):
        raise AppError(422, "ocr_failed", "Tesseract could not process this image.")

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_perform_ocr", fail)
    page = upload_pages(client, project["id"], ["proposal-failed.png"])[0]
    run = _run_ocr(client, project["id"], page["id"])
    assert run["status"] == "failed"

    body = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    ).json()
    assert body["status"] == "ocr_failed"
    assert body["proposals"] == []
