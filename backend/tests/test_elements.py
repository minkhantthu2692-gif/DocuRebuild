from __future__ import annotations

import io
import subprocess

from fastapi.testclient import TestClient
from PIL import Image

from tests.conftest import upload_pages


def _engine(available: bool = True, languages: list[str] | None = None) -> dict:
    installed = languages if languages is not None else ["eng", "mya"]
    return {
        "engine": "tesseract",
        "available": available,
        "version": "5.3.3" if available else None,
        "command": "tesseract",
        "tessdata_dir": None,
        "languages": installed if available else [],
        "preferred_languages": [code for code in ("eng", "mya") if code in installed]
        if available
        else [],
        "reason": None if available else "not_found",
        "setup_hint": None if available else "Install Tesseract locally.",
    }


def _tsv(*words: tuple[str, float]) -> str:
    header = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext"
    )
    rows = [header]
    for index, (text, confidence) in enumerate(words, start=1):
        rows.append(
            f"5\t1\t1\t1\t1\t{index}\t{index * 40}\t0\t36\t22\t{confidence}\t{text}"
        )
    return "\n".join(rows)


def _fake_text_run(tsv: str):
    def run(args, timeout):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=tsv, stderr="")

    return run


def _create(
    client: TestClient,
    project_id: str,
    page_id: str,
    **overrides,
) -> dict:
    payload = {
        "kind": "figure",
        "x": 100,
        "y": 120,
        "width": 300,
        "height": 200,
        "caption": "Figure 1. A local crop",
    }
    payload.update(overrides)
    response = client.post(
        f"/api/projects/{project_id}/pages/{page_id}/elements", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_element_crops_the_page_asset(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["element-page.png"])[0]
    element = _create(client, project["id"], page["id"])

    assert element["page_id"] == page["id"]
    assert element["kind"] == "figure"
    assert element["caption"] == "Figure 1. A local crop"
    assert element["source"] == "manual"
    assert element["verified"] is False
    assert element["stale"] is False
    assert (element["x"], element["y"], element["width"], element["height"]) == (
        100,
        120,
        300,
        200,
    )

    asset = client.get(
        f"/api/projects/{project['id']}/assets/{element['asset_id']}/file"
    )
    assert asset.status_code == 200, asset.text
    assert asset.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(asset.content)) as crop:
        assert crop.size == (300, 200)
        assert crop.mode in {"RGB", "RGBA"}

    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [element["id"]]


def test_create_element_rejects_invalid_regions(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["element-bounds.png"])[0]
    base = f"/api/projects/{project['id']}/pages/{page['id']}/elements"

    outside = client.post(
        base,
        json={
            "kind": "figure",
            "x": 1100,
            "y": 100,
            "width": 300,
            "height": 100,
        },
    )
    assert outside.status_code == 422
    assert outside.json()["detail"]["code"] == "element_region_invalid"

    tiny = client.post(
        base,
        json={"kind": "table", "x": 10, "y": 10, "width": 4, "height": 4},
    )
    assert tiny.status_code == 422
    assert tiny.json()["detail"]["code"] == "element_region_too_small"

    negative = client.post(
        base,
        json={"kind": "equation", "x": -1, "y": 10, "width": 80, "height": 80},
    )
    assert negative.status_code == 422

    listed = client.get(base)
    assert listed.status_code == 200
    assert listed.json() == []


def test_element_update_and_staleness_after_page_change(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["element-stale.png"])[0]
    element = _create(client, project["id"], page["id"], kind="table")

    updated = client.patch(
        f"/api/projects/{project['id']}/elements/{element['id']}",
        json={"caption": "Table 2. Reviewed caption", "verified": True},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["caption"] == "Table 2. Reviewed caption"
    assert body["verified"] is True
    assert body["stale"] is False

    rotated = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/rotate",
        json={"degrees": 90},
    )
    assert rotated.status_code == 200, rotated.text

    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    ).json()
    assert listed[0]["stale"] is True
    # The crop remains available and unchanged after the page changed.
    asset = client.get(
        f"/api/projects/{project['id']}/assets/{element['asset_id']}/file"
    )
    assert asset.status_code == 200
    with Image.open(io.BytesIO(asset.content)) as crop:
        assert crop.size == (300, 200)


def test_delete_element_moves_the_crop_to_trash(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["element-delete.png"])[0]
    element = _create(client, project["id"], page["id"])

    deleted = client.delete(
        f"/api/projects/{project['id']}/elements/{element['id']}"
    )
    assert deleted.status_code == 200, deleted.text

    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    )
    assert listed.status_code == 200
    assert listed.json() == []

    asset = client.get(
        f"/api/projects/{project['id']}/assets/{element['asset_id']}/file"
    )
    assert asset.status_code in {403, 404}

    missing = client.patch(
        f"/api/projects/{project['id']}/elements/{element['id']}",
        json={"verified": True},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "element_not_found"


def test_deleting_a_page_cleans_up_its_element_crops(
    client: TestClient, project: dict
) -> None:
    from pathlib import Path

    page = upload_pages(client, project["id"], ["element-page-delete.png"])[0]
    element = _create(client, project["id"], page["id"])
    directory = Path(client.get(f"/api/projects/{project['id']}").json()["directory"])
    crop_path = directory / "processed" / "elements" / f"{element['id']}.png"
    assert crop_path.exists()

    response = client.delete(f"/api/projects/{project['id']}/pages/{page['id']}")
    assert response.status_code == 200, response.text

    assert not crop_path.exists()
    trashed = directory / "trash" / page["id"] / f"{element['id']}.png"
    assert trashed.exists()
    asset = client.get(
        f"/api/projects/{project['id']}/assets/{element['asset_id']}/file"
    )
    assert asset.status_code in {403, 404}


def test_extract_element_text_stores_an_unverified_proposal(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine())
    monkeypatch.setattr(
        ocr,
        "_run_command",
        _fake_text_run(_tsv(("Figure", 94.0), ("2.4", 82.0), ("Diagram", 88.0))),
    )

    page = upload_pages(client, project["id"], ["element-text.png"])[0]
    element = _create(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/text",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "Figure 2.4 Diagram"
    assert body["text_confidence"] == 88.0
    assert body["text_engine"] == "tesseract"
    assert body["text_engine_version"] == "5.3.3"
    assert body["text_languages"] == ["eng"]
    assert body["text_corrected"] is False
    assert body["text_updated_at"]

    corrected = client.patch(
        f"/api/projects/{project['id']}/elements/{element['id']}/text",
        json={"text": "Figure 2.4 - Diagram (reviewed)"},
    )
    assert corrected.status_code == 200, corrected.text
    corrected_body = corrected.json()
    assert corrected_body["text"] == "Figure 2.4 - Diagram (reviewed)"
    assert corrected_body["text_corrected"] is True
    # The OCR provenance stays attached to the corrected text.
    assert corrected_body["text_engine"] == "tesseract"
    assert corrected_body["text_languages"] == ["eng"]

    listed = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/elements"
    ).json()
    assert listed[0]["text"] == "Figure 2.4 - Diagram (reviewed)"
    assert listed[0]["text_corrected"] is True


def test_extract_element_text_keeps_an_empty_result(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine())
    monkeypatch.setattr(ocr, "_run_command", _fake_text_run(_tsv()))

    page = upload_pages(client, project["id"], ["element-text-empty.png"])[0]
    element = _create(client, project["id"], page["id"], kind="table")
    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/text",
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == ""
    assert body["text_confidence"] is None
    assert body["text_engine"] == "tesseract"
    assert body["text_corrected"] is False


def test_extract_element_text_requires_an_available_engine(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(
        ocr, "detect_engine", lambda force=False: _engine(available=False)
    )
    page = upload_pages(client, project["id"], ["element-text-off.png"])[0]
    element = _create(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/text",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_unavailable"


def test_extract_element_text_rejects_missing_language_data(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(
        ocr, "detect_engine", lambda force=False: _engine(languages=["eng"])
    )
    page = upload_pages(client, project["id"], ["element-text-lang.png"])[0]
    element = _create(client, project["id"], page["id"])

    response = client.post(
        f"/api/projects/{project['id']}/elements/{element['id']}/text",
        json={"languages": ["mya"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_language_unavailable"
