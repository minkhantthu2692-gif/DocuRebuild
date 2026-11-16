from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.services import table_structure
from tests.conftest import upload_pages


def _engine_available() -> dict:
    return {
        "engine": "tesseract",
        "available": True,
        "version": "5.3.3",
        "command": "tesseract",
        "tessdata_dir": None,
        "languages": ["eng", "mya"],
        "preferred_languages": ["eng", "mya"],
        "reason": None,
        "setup_hint": None,
    }


def _word(
    text: str,
    x: int,
    y: int,
    *,
    width: int = 40,
    height: int = 20,
    confidence: float | None = 90.0,
    line: int = 0,
) -> dict:
    return {
        "text": text,
        "confidence": confidence,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "line": line,
    }


def _table_result(words: list[dict], *, kind: str = "table") -> dict:
    return {
        "engine_version": "5.3.3",
        "text": "Name Value\nMass 2\nLength",
        "mean_confidence": 90.0,
        "blocks": [
            {
                "block_index": 1,
                "kind": kind,
                "text": "Name Value\nMass 2\nLength",
                "confidence": 90.0,
                "x": 0,
                "y": 90,
                "width": 300,
                "height": 100,
                "line_count": 3,
                "word_count": 5,
                "words": words,
            }
        ],
    }


def _grid_words() -> list[dict]:
    return [
        _word("Name", 0, 100, line=0),
        _word("Value", 200, 100, confidence=95.0, line=0),
        _word("Mass", 0, 130, confidence=88.0, line=1),
        _word("2", 205, 130, width=10, confidence=40.0, line=1),
        _word("Length", 0, 160, width=60, confidence=90.0, line=2),
    ]


def _wait_for_run(
    client: TestClient, project_id: str, page_id: str, timeout: float = 5.0
) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/projects/{project_id}/pages/{page_id}/ocr")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest and latest["status"] in {"succeeded", "failed"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"OCR run did not finish: {latest}")


def _run_table_ocr(
    client: TestClient, project: dict, monkeypatch, result: dict
) -> tuple[dict, dict]:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_perform_ocr", lambda *args, **kwargs: result)
    page = upload_pages(client, project["id"], ["table-page.png"])[0]
    response = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 202, response.text
    run = _wait_for_run(client, project["id"], page["id"])
    assert run["status"] == "succeeded", run
    return page, run


def test_proposal_builds_a_reviewable_grid(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _run_table_ocr(client, project, monkeypatch, _table_result(_grid_words()))
    block = run["blocks"][0]

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 200, response.text
    proposal = response.json()

    assert proposal["rows"] == 3
    assert proposal["columns"] == 2
    assert proposal["has_confidence"] is True
    assert proposal["uncertain_cells"] == 1
    assert proposal["empty_cells"] == 1
    assert set(proposal["warnings"]) == {"low_confidence", "empty_cells"}

    cells = {(cell["row"], cell["column"]): cell for cell in proposal["cells"]}
    assert cells[(0, 0)]["text"] == "Name"
    assert cells[(0, 1)]["text"] == "Value"
    assert cells[(1, 0)]["text"] == "Mass"
    assert cells[(1, 1)]["text"] == "2"
    assert cells[(1, 1)]["confidence"] == 40.0
    assert cells[(1, 1)]["uncertain"] is True
    assert cells[(2, 0)]["text"] == "Length"
    assert cells[(2, 1)]["text"] == ""
    assert cells[(2, 1)]["empty"] is True
    # An empty cell is not "uncertain": there is simply no content to check.
    assert cells[(2, 1)]["uncertain"] is False


def test_proposal_is_refused_after_a_manual_correction(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _run_table_ocr(client, project, monkeypatch, _table_result(_grid_words()))
    block = run["blocks"][0]

    corrected = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr/blocks/{block['id']}",
        json={"text": "Name Value\nMass 3"},
    )
    assert corrected.status_code == 200, corrected.text

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "table_source_modified"


def test_proposal_requires_a_table_block(
    client: TestClient, project: dict, monkeypatch
) -> None:
    result = _table_result(_grid_words(), kind="paragraph")
    page, run = _run_table_ocr(client, project, monkeypatch, result)
    block = run["blocks"][0]

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "table_block_required"


def test_proposal_is_refused_when_the_result_is_stale(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _run_table_ocr(client, project, monkeypatch, _table_result(_grid_words()))
    block = run["blocks"][0]
    rotated = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/rotate",
        json={"degrees": 90},
    )
    assert rotated.status_code == 200

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_stale"


def test_proposal_reports_when_word_positions_are_missing(
    client: TestClient, project: dict, monkeypatch
) -> None:
    result = _table_result([])
    page, run = _run_table_ocr(client, project, monkeypatch, result)
    block = run["blocks"][0]

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "table_no_words"


def test_proposal_refuses_a_grid_that_is_too_large(
    client: TestClient, project: dict, monkeypatch
) -> None:
    words = []
    for row in range(table_structure.MAX_ROWS + 1):
        line = row
        words.append(_word("Left", 0, row * 30, line=line))
        words.append(_word("Right", 200, row * 30, line=line))
    page, run = _run_table_ocr(client, project, monkeypatch, _table_result(words))
    block = run["blocks"][0]

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "table_too_large"


def test_parse_words_skips_malformed_entries() -> None:
    words = table_structure._parse_words(
        """
        [
          {"text": "Good", "x": 0, "y": 0, "width": 10, "height": 10,
           "confidence": 88, "line": 0},
          {"text": "", "x": 0, "y": 0, "width": 10, "height": 10},
          {"text": "NoBox", "x": 0, "y": 0},
          {"text": "BadConfidence", "x": 0, "y": 0, "width": 10, "height": 10,
           "confidence": "high"},
          "not an object"
        ]
        """
    )
    assert [word["text"] for word in words] == ["Good", "BadConfidence"]
    assert words[0]["confidence"] == 88.0
    assert words[1]["confidence"] is None
    assert table_structure._parse_words("not json") == []


def test_row_clustering_keeps_baseline_variation_in_one_row() -> None:
    rows = table_structure._cluster_rows(
        [
            _word("A", 0, 100, height=20),
            _word("B", 100, 104, height=20),
            _word("C", 0, 140, height=20),
        ]
    )
    assert [[word["text"] for word in row] for row in rows] == [["A", "B"], ["C"]]
