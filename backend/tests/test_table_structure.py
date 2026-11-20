from __future__ import annotations

import io
import time

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.services import table_structure
from tests.conftest import upload_pages
from tests.test_pdf import upload_pdf


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


def _alignment_words() -> list[dict]:
    return [
        _word("Name", 0, 100, width=100, line=0),
        _word("Value", 200, 100, width=100, line=0),
        _word("Number", 400, 100, width=100, line=0),
        _word("Mass", 0, 130, width=40, line=1),
        _word("2", 240, 130, width=20, line=1),
        _word("7", 480, 130, width=20, line=1),
    ]


def _ruled_block_words() -> list[dict]:
    """Words inside the 2-row, 3-column ruled table drawn by the tests below."""
    return [
        _word("Merged", 120, 100, width=60, line=0),
        _word("A", 20, 150, width=20, line=1),
        _word("B", 120, 150, width=20, line=1),
        _word("C", 220, 150, width=20, line=1),
    ]


def _unaligned_ruled_words() -> list[dict]:
    """Rows whose wide gaps sit at different places, so no table is inferred."""
    return [
        _word("Alpha", 20, 100, width=60, line=0),
        _word("Beta", 220, 100, width=60, line=0),
        _word("Gamma", 20, 150, width=60, line=1),
        _word("Delta", 120, 150, width=60, line=1),
    ]


def _paragraph_group_result() -> dict:
    """A paragraph block holding a ruled table, then a prose block below it."""
    return {
        "engine_version": "5.3.3",
        "text": "Alpha Beta\nGamma Delta\nTail",
        "mean_confidence": 90.0,
        "blocks": [
            {
                "block_index": 1,
                "kind": "paragraph",
                "text": "Alpha Beta\nGamma Delta",
                "confidence": 90.0,
                "x": 0,
                "y": 90,
                "width": 300,
                "height": 100,
                "line_count": 2,
                "word_count": 4,
                "words": _unaligned_ruled_words(),
            },
            {
                "block_index": 2,
                "kind": "paragraph",
                "text": "Tail",
                "confidence": 90.0,
                "x": 240,
                "y": 196,
                "width": 60,
                "height": 20,
                "line_count": 1,
                "word_count": 1,
                "words": [_word("Tail", 250, 200, width=40, line=0)],
            },
        ],
    }


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
    client: TestClient,
    project: dict,
    monkeypatch,
    result: dict,
    page_png: bytes | None = None,
    page: dict | None = None,
) -> tuple[dict, dict]:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_perform_ocr", lambda *args, **kwargs: result)
    if page is None:
        if page_png is None:
            page = upload_pages(client, project["id"], ["table-page.png"])[0]
        else:
            page = _upload_png(client, project["id"], "table-rules.png", page_png)
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
    assert proposal["page_width"] == 1200
    assert proposal["page_height"] == 800
    # The source box covers exactly the words that were read, so the review
    # dialog can crop the page without guessing.
    assert proposal["source"] == {"x": 0.0, "y": 100.0, "width": 240.0, "height": 80.0}

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
    assert cells[(2, 1)]["alignment"] is None


def test_block_proposal_keeps_merged_cells_from_drawn_rules(
    client: TestClient, project: dict, monkeypatch
) -> None:
    # The fake block below covers 0,90 300x100, so the rules sit two pixels
    # inside that box on the uploaded page.
    page_png = _png_with_table_rules(
        left=2, top=92, right=298, bottom=188, columns=3, merge_top_header=True
    )
    page, run = _run_table_ocr(
        client,
        project,
        monkeypatch,
        _table_result(_ruled_block_words()),
        page_png=page_png,
    )
    block = run["blocks"][0]

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 200, response.text
    proposal = response.json()

    assert proposal["rows"] == 2
    assert proposal["columns"] == 3
    cells = {(cell["row"], cell["column"]): cell for cell in proposal["cells"]}
    assert cells[(0, 1)]["text"] == "Merged"
    assert cells[(0, 1)]["colspan"] == 2
    assert cells[(1, 0)]["text"] == "A"
    assert cells[(1, 1)]["text"] == "B"
    assert cells[(1, 2)]["text"] == "C"
    # The source is the drawn table, which starts left of the text-block box.
    assert proposal["source"]["x"] < 5
    assert proposal["source"]["width"] > 290


def test_page_candidates_keep_merged_cells_from_drawn_rules(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page_png = _png_with_table_rules(
        left=2, top=92, right=298, bottom=188, columns=3, merge_top_header=True
    )
    page, run = _run_table_ocr(
        client,
        project,
        monkeypatch,
        _table_result(_ruled_block_words()),
        page_png=page_png,
    )

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 200, response.text
    candidates = response.json()["candidates"]

    # One table is one candidate: the ruled grid replaces the coarser word grid
    # instead of being listed beside it.
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["rows"] == 2
    assert candidate["columns"] == 3
    assert candidate["block_ids"] == [run["blocks"][0]["id"]]
    cells = {(cell["row"], cell["column"]): cell for cell in candidate["cells"]}
    assert cells[(0, 1)]["colspan"] == 2
    assert cells[(1, 2)]["text"] == "C"


def test_page_candidates_read_a_ruled_group_without_clean_columns(
    client: TestClient, project: dict, monkeypatch
) -> None:
    # Each row has a wide gap, but the two gaps do not share a position, so the
    # word geometry is not accepted as a table. The drawn borders still are.
    page_png = _png_with_table_rules(
        left=2, top=92, right=298, bottom=188, columns=3
    )
    page, run = _run_table_ocr(
        client,
        project,
        monkeypatch,
        _paragraph_group_result(),
        page_png=page_png,
    )

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 200, response.text
    candidates = response.json()["candidates"]

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["rows"] == 2
    assert candidate["columns"] == 3
    # The prose block below the table is outside the grid, so it contributes no
    # cell and is not treated as table content.
    assert candidate["block_ids"] == [run["blocks"][0]["id"]]
    cells = {(cell["row"], cell["column"]): cell for cell in candidate["cells"]}
    assert cells[(0, 0)]["text"] == "Alpha"
    assert cells[(0, 1)]["empty"] is True
    assert cells[(0, 2)]["text"] == "Beta"
    assert cells[(1, 0)]["text"] == "Gamma"
    assert cells[(1, 1)]["text"] == "Delta"
    assert candidate["source"]["x"] < 5
    assert candidate["source"]["height"] < 110


def test_proposal_reports_only_observable_cell_alignment(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _run_table_ocr(
        client, project, monkeypatch, _table_result(_alignment_words())
    )
    block = run["blocks"][0]

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 200, response.text
    cells = {(cell["row"], cell["column"]): cell for cell in response.json()["cells"]}

    assert cells[(1, 0)]["alignment"] == "left"
    assert cells[(1, 1)]["alignment"] == "center"
    assert cells[(1, 2)]["alignment"] == "right"
    # The header words fill their column bands, so no alignment is claimed for
    # them instead of guessing from a single edge.
    assert cells[(0, 0)]["alignment"] is None
    assert cells[(0, 1)]["alignment"] is None
    assert cells[(0, 2)]["alignment"] is None


def test_cell_alignment_requires_agreeing_lines() -> None:
    lines = {
        0: [_word("Left", 200, 100, width=20)],
        1: [_word("Centre", 240, 106, width=20)],
    }
    assert table_structure._cell_alignment(lines, (200, 300), 20) is None


def test_cell_alignment_skips_a_line_that_fills_the_band() -> None:
    lines = {
        0: [_word("Full", 200, 100, width=100)],
        1: [_word("Mid", 240, 106, width=20)],
    }
    assert table_structure._cell_alignment(lines, (200, 300), 20) == "center"
    assert table_structure._cell_alignment(lines, None, 20) is None


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


def _rows_result(
    rows: list[list[tuple[str, int, int]]],
    *,
    kind: str = "paragraph",
    confidence: float | None = 90.0,
) -> dict:
    """Build one block per visual row, the way embedded PDF text often arrives."""
    blocks = []
    for index, row in enumerate(rows):
        y = 100 + index * 30
        words = [
            _word(text, x, y, width=width, confidence=confidence, line=0)
            for text, x, width in row
        ]
        left = min(item[1] for item in row)
        right = max(item[1] + item[2] for item in row)
        blocks.append(
            {
                "block_index": index + 1,
                "kind": kind,
                "text": " ".join(item[0] for item in row),
                "confidence": confidence,
                "x": left,
                "y": y,
                "width": right - left,
                "height": 20,
                "line_count": 1,
                "word_count": len(row),
                "words": words,
            }
        )
    return {
        "engine_version": "5.3.3",
        "text": "\n".join(" ".join(item[0] for item in row) for row in rows),
        "mean_confidence": confidence,
        "blocks": blocks,
    }


def _row_table_rows() -> list[list[tuple[str, int, int]]]:
    return [
        [("Element", 0, 70), ("Symbol", 200, 60)],
        [("Hydrogen", 0, 80), ("H", 200, 10)],
        [("Helium", 0, 60), ("He", 200, 15)],
    ]


def _crop_tsv(
    rows: list[list[tuple[str, int, int, float]]],
) -> str:
    """Build engine TSV in crop coordinates, one block per visual row."""
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext"
    )
    lines = [header]
    for row_index, row in enumerate(rows):
        top = 10 + row_index * 30
        for column_index, (text, left, width, confidence) in enumerate(row):
            lines.append(
                f"5\t1\t{row_index + 1}\t1\t1\t{column_index + 1}\t"
                f"{left}\t{top}\t{width}\t20\t{confidence}\t{text}"
            )
    return "\n".join(lines)


def _fake_crop_ocr(tsv: str):
    import subprocess

    def run(args, timeout):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=tsv, stderr="")

    return run


def _crop_word_tsv(
    words: list[tuple[str, int, int, int, int, float]],
) -> str:
    """Build engine TSV at explicit crop coordinates.

    Each tuple is ``(text, left, top, width, height, confidence)``. All words
    share one block, which is the harsher case for joining a visual row.
    """
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext"
    )
    lines = [header]
    for index, (text, left, top, width, height, confidence) in enumerate(words):
        lines.append(
            f"5\t1\t1\t1\t1\t{index + 1}\t{left}\t{top}\t{width}\t{height}\t"
            f"{confidence}\t{text}"
        )
    return "\n".join(lines)


def _png_with_table_rules(
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    columns: int,
    merge_top_header: bool = False,
) -> bytes:
    """Return a page PNG with a two-row table drawn as filled rules.

    The caller positions the rectangle inside the region that
    :func:`_create_table_element` crops, so every border survives the crop.
    """
    image = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([left, top, right, bottom], outline="black", width=3)
    middle = (top + bottom) // 2
    draw.line([left, middle, right, middle], fill="black", width=3)
    for index in range(1, columns):
        x = left + round((right - left) * index / columns)
        if merge_top_header and index == columns - 1:
            # The top row omits this separator, so those two cells are merged.
            draw.line([x, middle, x, bottom], fill="black", width=3)
        else:
            draw.line([x, top, x, bottom], fill="black", width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_png(
    client: TestClient, project_id: str, name: str, content: bytes
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/pages/import",
        files=[("files", (name, content, "image/png"))],
    )
    assert response.status_code == 200, response.text
    return response.json()[0]


def _create_table_element(
    client: TestClient, project_id: str, page_id: str, **overrides
) -> dict:
    payload = {
        "kind": "table",
        "x": 40,
        "y": 120,
        "width": 300,
        "height": 120,
        "caption": "",
    }
    payload.update(overrides)
    response = client.post(
        f"/api/projects/{project_id}/pages/{page_id}/elements", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def _crop_rows() -> list[list[tuple[str, int, int, float]]]:
    return [
        [("Item", 10, 50, 90.0), ("Qty", 150, 30, 95.0)],
        [("Green", 10, 50, 88.0), ("apples", 65, 55, 90.0), ("3", 150, 10, 40.0)],
    ]


def test_element_table_reads_a_saved_crop_locally(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_run_command", _fake_crop_ocr(_crop_tsv(_crop_rows())))
    page = upload_pages(client, project["id"], ["crop-table.png"])[0]
    element = _create_table_element(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/table-proposal",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 200, response.text
    proposal = response.json()

    assert proposal["element_id"] == element["id"]
    assert proposal["page_id"] == page["id"]
    assert proposal["engine"] == "tesseract"
    assert proposal["engine_version"] == "5.3.3"
    assert proposal["languages"] == ["eng"]
    assert proposal["rows"] == 2
    assert proposal["columns"] == 2
    assert proposal["has_confidence"] is True
    assert proposal["uncertain_cells"] == 1
    assert proposal["empty_cells"] == 0
    assert proposal["warnings"] == ["low_confidence"]
    # The preview positions the saved region on the page image, not the crop's
    # own coordinates.
    assert proposal["source"] == {"x": 40.0, "y": 120.0, "width": 300.0, "height": 120.0}
    assert proposal["page_width"] == 1200
    assert proposal["page_height"] == 800

    cells = {(cell["row"], cell["column"]): cell for cell in proposal["cells"]}
    assert cells[(0, 0)]["text"] == "Item"
    assert cells[(0, 1)]["text"] == "Qty"
    # Words that share a visual row are joined, even when OCR split them into
    # different blocks.
    assert cells[(1, 0)]["text"] == "Green apples"
    assert cells[(1, 1)]["text"] == "3"
    assert cells[(1, 1)]["confidence"] == 40.0
    assert cells[(1, 1)]["uncertain"] is True

    # Reading the crop is a proposal only: the element and document are untouched.
    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    ).json()
    assert listed[0]["text"] == ""


def test_element_table_requires_a_saved_table_region(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_run_command", _fake_crop_ocr(_crop_tsv(_crop_rows())))
    page = upload_pages(client, project["id"], ["crop-figure.png"])[0]
    element = _create_table_element(client, project["id"], page["id"], kind="figure")

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/table-proposal",
        json={},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "table_element_required"


def test_element_table_reports_an_empty_crop(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_run_command", _fake_crop_ocr(_crop_tsv([])))
    page = upload_pages(client, project["id"], ["crop-empty.png"])[0]
    element = _create_table_element(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/table-proposal",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "table_crop_empty"


def test_element_table_rejects_a_single_column_crop(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    rows = [
        [("Name", 10, 50, 90.0)],
        [("Mass", 10, 50, 90.0)],
    ]
    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_run_command", _fake_crop_ocr(_crop_tsv(rows)))
    page = upload_pages(client, project["id"], ["crop-column.png"])[0]
    element = _create_table_element(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/table-proposal",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "table_crop_not_detected"


def test_element_table_requires_the_local_engine(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(
        ocr,
        "detect_engine",
        lambda force=False: {
            **_engine_available(),
            "available": False,
            "languages": [],
            "reason": "not_found",
        },
    )
    page = upload_pages(client, project["id"], ["crop-no-engine.png"])[0]
    element = _create_table_element(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/table-proposal",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_unavailable"


def test_element_table_keeps_merged_cells_from_drawn_rules(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    # The rules sit two pixels inside the region cropped below: 40,120 300x120.
    page_png = _png_with_table_rules(
        left=42, top=122, right=338, bottom=238, columns=3, merge_top_header=True
    )
    tsv = _crop_word_tsv(
        [
            ("Merged", 170, 20, 70, 20, 90.0),
            ("A", 30, 80, 20, 20, 90.0),
            ("B", 130, 80, 20, 20, 90.0),
            ("C", 230, 80, 20, 20, 90.0),
        ]
    )
    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_run_command", _fake_crop_ocr(tsv))
    page = _upload_png(client, project["id"], "crop-rules-merged.png", page_png)
    element = _create_table_element(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/table-proposal",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 200, response.text
    proposal = response.json()

    assert proposal["rows"] == 2
    assert proposal["columns"] == 3
    assert proposal["empty_cells"] == 1
    assert proposal["source"] == {
        "x": 40.0,
        "y": 120.0,
        "width": 300.0,
        "height": 120.0,
    }

    # The top row's missing separator is the document's own merge, not a guess:
    # the empty top-left cell is not borrowed by the merged header beside it.
    cells = {(cell["row"], cell["column"]): cell for cell in proposal["cells"]}
    assert len(cells) == 5
    assert cells[(0, 0)]["empty"] is True
    assert cells[(0, 1)]["text"] == "Merged"
    assert cells[(0, 1)]["colspan"] == 2
    assert cells[(1, 0)]["text"] == "A"
    assert cells[(1, 1)]["text"] == "B"
    assert cells[(1, 2)]["text"] == "C"


def test_element_table_keeps_every_word_when_a_word_sits_outside_the_rules(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    # A closed 2x2 grid, but one detected word lies outside it. Using the rules
    # would silently drop that word, so the word-box grid must take over.
    page_png = _png_with_table_rules(
        left=70, top=140, right=310, bottom=230, columns=2
    )
    tsv = _crop_word_tsv(
        [
            ("Stray", 5, 5, 20, 20, 90.0),
            ("A", 45, 35, 20, 20, 90.0),
            ("B", 150, 35, 20, 20, 90.0),
            ("C", 45, 80, 20, 20, 90.0),
            ("D", 150, 80, 20, 20, 90.0),
        ]
    )
    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_run_command", _fake_crop_ocr(tsv))
    page = _upload_png(client, project["id"], "crop-rules-stray.png", page_png)
    element = _create_table_element(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/table-proposal",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 200, response.text
    proposal = response.json()

    texts = [cell["text"] for cell in proposal["cells"]]
    assert "Stray" in texts
    assert all(cell.get("colspan", 1) == 1 for cell in proposal["cells"])
    assert all(cell.get("rowspan", 1) == 1 for cell in proposal["cells"])


def test_page_candidates_merge_adjacent_row_blocks(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _run_table_ocr(
        client, project, monkeypatch, _rows_result(_row_table_rows())
    )

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["run_id"] == run["id"]
    assert data["page_width"] == 1200
    assert data["page_height"] == 800
    assert len(data["candidates"]) == 1
    candidate = data["candidates"][0]
    assert candidate["block_ids"] == [block["id"] for block in run["blocks"]]
    assert candidate["rows"] == 3
    assert candidate["columns"] == 2
    assert candidate["source"] == {"x": 0.0, "y": 100.0, "width": 260.0, "height": 80.0}
    cells = {(cell["row"], cell["column"]): cell for cell in candidate["cells"]}
    assert cells[(0, 0)]["text"] == "Element"
    assert cells[(0, 1)]["text"] == "Symbol"
    assert cells[(2, 0)]["text"] == "Helium"
    assert cells[(2, 1)]["text"] == "He"
    assert candidate["warnings"] == []


def test_page_candidates_do_not_merge_unrelated_paragraphs(
    client: TestClient, project: dict, monkeypatch
) -> None:
    result = _rows_result(
        [
            [("Introduction", 0, 120)],
            [("This", 0, 40), ("is", 45, 20), ("body", 70, 45), ("text", 120, 40)],
        ]
    )
    page, _run = _run_table_ocr(client, project, monkeypatch, result)

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 200, response.text
    assert response.json()["candidates"] == []


def test_page_candidates_include_a_single_table_block(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _run_table_ocr(client, project, monkeypatch, _table_result(_grid_words()))

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 200, response.text
    candidates = response.json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["block_ids"] == [run["blocks"][0]["id"]]
    assert candidates[0]["rows"] == 3
    assert candidates[0]["columns"] == 2


def test_page_candidates_skip_a_corrected_block(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, run = _run_table_ocr(
        client, project, monkeypatch, _rows_result(_row_table_rows())
    )
    corrected = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{run['blocks'][1]['id']}",
        json={"text": "Hydrogen H corrected"},
    )
    assert corrected.status_code == 200, corrected.text

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 200, response.text
    assert response.json()["candidates"] == []


def test_page_candidates_require_a_finished_run(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["no-ocr.png"])[0]

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_not_ready"


def test_page_candidates_are_refused_when_the_result_is_stale(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page, _run = _run_table_ocr(
        client, project, monkeypatch, _rows_result(_row_table_rows())
    )
    rotated = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/rotate",
        json={"degrees": 90},
    )
    assert rotated.status_code == 200

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_stale"


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


def _merged_rule_grid() -> tuple[
    list[tuple[float, float, float]], list[tuple[float, float, float]]
]:
    """A 3x3 grid with a full-width header and a two-row cell in column 0."""
    horizontals = [
        (100.0, 50.0, 550.0),
        (150.0, 50.0, 550.0),
        # Missing between the two data rows in column 0, so that cell spans them.
        (250.0, 250.0, 550.0),
        (350.0, 50.0, 550.0),
    ]
    verticals = [
        (50.0, 100.0, 350.0),
        # The column separators start below the merged header row.
        (250.0, 150.0, 350.0),
        (400.0, 150.0, 350.0),
        (550.0, 100.0, 350.0),
    ]
    return horizontals, verticals


def _merged_rule_words() -> list[tuple[str, dict]]:
    return [
        ("b1", _word("Merged", 60, 132, width=40, height=16, confidence=None, line=0)),
        ("b1", _word("header", 110, 132, width=40, height=16, confidence=None, line=0)),
        # Both words land in the row-spanning cell but their stored line numbers
        # collide with the header's, so the cell must re-line them by position.
        ("b2", _word("Group", 60, 200, width=40, height=16, confidence=None, line=0)),
        ("b3", _word("A", 60, 300, width=10, height=16, confidence=None, line=0)),
        ("b2", _word("1.2", 260, 200, width=20, height=16, confidence=None, line=0)),
        ("b2", _word("3.4", 410, 200, width=20, height=16, confidence=None, line=0)),
        ("b3", _word("5.6", 260, 300, width=20, height=16, confidence=None, line=0)),
        ("b3", _word("7.8", 410, 300, width=20, height=16, confidence=None, line=0)),
    ]


def test_vector_candidates_derive_merged_cells_from_missing_rules() -> None:
    horizontals, verticals = _merged_rule_grid()

    candidates = table_structure._vector_candidates(
        horizontals, verticals, _merged_rule_words()
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["rows"] == 3
    assert candidate["columns"] == 3
    assert candidate["block_ids"] == ["b1", "b2", "b3"]
    assert candidate["source"] == {"x": 50.0, "y": 100.0, "width": 500.0, "height": 250.0}
    assert candidate["warnings"] == ["no_confidence"]
    assert candidate["uncertain_cells"] == 0
    assert candidate["empty_cells"] == 0

    cells = {(cell["row"], cell["column"]): cell for cell in candidate["cells"]}
    # Covered coordinates are not cells; only the anchor carries the span.
    assert len(cells) == 6
    assert cells[(0, 0)]["rowspan"] == 1
    assert cells[(0, 0)]["colspan"] == 3
    assert cells[(0, 0)]["text"] == "Merged header"
    assert cells[(1, 0)]["rowspan"] == 2
    assert cells[(1, 0)]["colspan"] == 1
    assert cells[(1, 0)]["text"] == "Group\nA"
    assert cells[(1, 0)]["alignment"] == "left"
    assert cells[(1, 1)]["text"] == "1.2"
    assert cells[(2, 2)]["text"] == "7.8"
    assert (0, 1) not in cells
    assert (2, 0) not in cells


def _plain_rule_grid(
    xs: list[float], ys: list[float]
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    horizontals = [(y, xs[0], xs[-1]) for y in ys]
    verticals = [(x, ys[0], ys[-1]) for x in xs]
    return horizontals, verticals


def test_vector_candidates_reject_an_empty_drawn_frame() -> None:
    horizontals, verticals = _plain_rule_grid([0.0, 100.0, 200.0], [0.0, 50.0, 100.0])

    # A chart's axis frame is a grid without table text. It must never become a
    # table candidate just because the rules exist.
    assert table_structure._vector_candidates(horizontals, verticals, []) == []


def test_vector_candidates_reject_a_large_grid_with_too_little_text() -> None:
    horizontals, verticals = _plain_rule_grid(
        [0.0, 100.0, 200.0, 300.0, 400.0, 500.0],
        [0.0, 50.0, 100.0, 150.0, 200.0, 250.0],
    )
    words = [
        ("b1", _word("A", 10, 10, width=20, height=16, confidence=None)),
        ("b1", _word("B", 110, 60, width=20, height=16, confidence=None)),
    ]

    # Two labels inside a 25-cell frame look more like a chart than a table.
    assert table_structure._vector_candidates(horizontals, verticals, words) == []


def test_vector_candidates_require_a_closed_grid() -> None:
    horizontals, verticals = _plain_rule_grid([0.0, 100.0, 200.0], [0.0, 50.0, 100.0])
    # Remove the right border: an open grid cannot bound its last column.
    verticals = [(x, y0, y1) for x, y0, y1 in verticals if x != 200.0]

    words = [
        ("b1", _word("A", 10, 10, width=20, height=16, confidence=None)),
        ("b1", _word("B", 110, 10, width=20, height=16, confidence=None)),
        ("b1", _word("C", 10, 60, width=20, height=16, confidence=None)),
        ("b1", _word("D", 110, 60, width=20, height=16, confidence=None)),
    ]

    assert table_structure._vector_candidates(horizontals, verticals, words) == []


def test_covered_ratio_measures_the_share_inside_a_vector_grid() -> None:
    grid = {"x": 50.0, "y": 100.0, "width": 500.0, "height": 250.0}
    inside = {"x": 60.0, "y": 110.0, "width": 100.0, "height": 50.0}
    half = {"x": 500.0, "y": 110.0, "width": 100.0, "height": 50.0}

    assert table_structure._covered_ratio(inside, grid) == 1.0
    assert table_structure._covered_ratio(half, grid) == 0.5


def _merged_table_pdf() -> bytes:
    """A PDF whose drawn rules merge the header and column 0's data rows."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        black = (0, 0, 0)
        for y in (100, 150, 350):
            page.draw_line((50, y), (550, y), color=black, width=0.8)
        page.draw_line((250, 250), (550, 250), color=black, width=0.8)
        for x in (50, 550):
            page.draw_line((x, 100), (x, 350), color=black, width=0.8)
        for x in (250, 400):
            page.draw_line((x, 150), (x, 350), color=black, width=0.8)

        page.insert_text((60, 138), "Merged header", fontsize=10)
        page.insert_text((60, 210), "Group", fontsize=10)
        page.insert_text((60, 310), "A", fontsize=10)
        page.insert_text((260, 210), "1.2", fontsize=10)
        page.insert_text((410, 210), "3.4", fontsize=10)
        page.insert_text((260, 310), "5.6", fontsize=10)
        page.insert_text((410, 310), "7.8", fontsize=10)
        return document.tobytes()
    finally:
        document.close()


def test_page_candidates_prefer_the_drawn_grid_with_merged_cells(
    client: TestClient, project: dict
) -> None:
    pages = upload_pdf(client, project["id"], "merged.pdf", _merged_table_pdf())
    page = pages[0]

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/table-proposals"
    )
    assert response.status_code == 200, response.text
    candidates = response.json()["candidates"]

    # The OCR candidate describing the same words is dropped in favour of the
    # exact rule grid, so one table is not offered twice.
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["rows"] == 3
    assert candidate["columns"] == 3
    cells = {(cell["row"], cell["column"]): cell for cell in candidate["cells"]}
    assert cells[(0, 0)]["colspan"] == 3
    assert cells[(0, 0)]["text"] == "Merged header"
    assert cells[(1, 0)]["rowspan"] == 2
    assert cells[(1, 0)]["text"] == "Group\nA"
    assert cells[(1, 1)]["text"] == "1.2"
    assert cells[(2, 1)]["text"] == "5.6"
    assert (0, 2) not in cells
    assert (2, 0) not in cells

    # These blocks are paragraphs, so only the page path may group them into a
    # table; the single-block path refuses an unlabelled block.
    block = candidate["block_ids"][0]
    single = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block}/table-proposal"
    )
    assert single.status_code == 422


def _merged_block_pdf() -> bytes:
    """A PDF whose rules merge column 0 across its two data rows.

    The grid is drawn at 50-500 x 80-320 points on a 600x800 page, so a page
    imported at 2x places it at 100-1000 x 160-640 display pixels.
    """
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        black = (0, 0, 0)
        xs = (50.0, 200.0, 350.0, 500.0)
        ys = (80.0, 160.0, 240.0, 320.0)
        for y in (ys[0], ys[1], ys[3]):
            page.draw_line((xs[0], y), (xs[3], y), color=black, width=0.8)
        # Column 0 has no separator between its two data rows, so they merge.
        page.draw_line((xs[1], ys[2]), (xs[3], ys[2]), color=black, width=0.8)
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[3]), color=black, width=0.8)
        page.insert_text((60, 110), "Group 1.2 3.4", fontsize=10)
        page.insert_text((60, 190), "A 5.6 7.8", fontsize=10)
        page.insert_text((60, 270), "B 9.1 2.3", fontsize=10)
        return document.tobytes()
    finally:
        document.close()


def _ruled_pdf_result() -> dict:
    """An OCR stub whose words sit inside the grid of ``_merged_block_pdf``."""
    words = [
        _word("Group", 120, 180, width=60, line=0),
        _word("1.2", 430, 180, width=30, line=0),
        _word("3.4", 730, 180, width=30, line=0),
        _word("A", 120, 350, width=20, line=1),
        _word("5.6", 430, 350, width=30, line=1),
        _word("7.8", 730, 350, width=30, line=1),
        _word("B", 120, 510, width=20, line=2),
        _word("9.1", 430, 510, width=30, line=2),
        _word("2.3", 730, 510, width=30, line=2),
    ]
    return {
        "engine_version": "5.3.3",
        "text": "Group 1.2 3.4\nA 5.6 7.8\nB 9.1 2.3",
        "mean_confidence": 90.0,
        "blocks": [
            {
                "block_index": 1,
                "kind": "table",
                "text": "Group 1.2 3.4\nA 5.6 7.8\nB 9.1 2.3",
                "confidence": 90.0,
                "x": 90,
                "y": 150,
                "width": 920,
                "height": 520,
                "line_count": 3,
                "word_count": len(words),
                "words": words,
            }
        ],
    }


def test_block_proposal_reads_the_pdf_drawn_grid(
    client: TestClient, project: dict, monkeypatch
) -> None:
    page = upload_pdf(client, project["id"], "ruled.pdf", _merged_block_pdf())[0]
    page, run = _run_table_ocr(
        client, project, monkeypatch, _ruled_pdf_result(), page=page
    )
    block = run["blocks"][0]
    assert block["kind"] == "table"

    response = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}"
        f"/ocr/blocks/{block['id']}/table-proposal"
    )
    assert response.status_code == 200, response.text
    proposal = response.json()

    assert proposal["rows"] == 3
    assert proposal["columns"] == 3
    cells = {(cell["row"], cell["column"]): cell for cell in proposal["cells"]}
    assert cells[(0, 0)]["text"] == "Group"
    assert cells[(0, 1)]["text"] == "1.2"
    assert cells[(0, 2)]["text"] == "3.4"
    assert cells[(1, 0)]["rowspan"] == 2
    assert cells[(1, 0)]["text"] == "A\nB"
    assert cells[(1, 1)]["text"] == "5.6"
    assert cells[(2, 1)]["text"] == "9.1"
    assert cells[(2, 2)]["text"] == "2.3"
    assert (2, 0) not in cells
    # The drawn grid is wider than the words, so the source comes from the PDF
    # rules rather than from the word-box extent.
    assert proposal["source"]["x"] < 105
    assert proposal["source"]["width"] > 890
