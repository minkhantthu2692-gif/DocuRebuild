from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_png, upload_pages


def make_pdf(pages: list[str]) -> bytes:
    document = pymupdf.open()
    try:
        for text in pages:
            page = document.new_page(width=595, height=842)
            if text:
                page.insert_text((72, 100), text, fontsize=14)
        return document.tobytes()
    finally:
        document.close()


def make_image_only_pdf() -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(72, 72, 500, 360), stream=make_png(600, 400))
        return document.tobytes()
    finally:
        document.close()


def upload_pdf(client: TestClient, project_id: str, name: str, data: bytes) -> list[dict]:
    response = client.post(
        f"/api/projects/{project_id}/pages/import",
        files=[("files", (name, data, "application/pdf"))],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_text_pdf_import_renders_pages_and_stores_embedded_text(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    data = make_pdf(["Hello PDF page one", "Second page body"])
    pages = upload_pdf(client, project_id, "book.pdf", data)

    assert [page["page_number"] for page in pages] == [1, 2]
    assert [page["pdf_page_number"] for page in pages] == [1, 2]
    assert all(page["source_kind"] == "pdf" for page in pages)
    assert all(page["status"] == "ready" for page in pages)
    assert all(page["original_filename"] == "book.pdf" for page in pages)
    assert all(page["width"] and page["width"] > 600 for page in pages)
    # Every page of one PDF shares the same immutable original asset.
    assert pages[0]["original_asset_id"] == pages[1]["original_asset_id"]
    assert pages[0]["display_asset_id"] != pages[1]["display_asset_id"]

    original = client.get(
        f"/api/projects/{project_id}/assets/{pages[0]['original_asset_id']}/file"
    )
    assert original.status_code == 200
    assert original.headers["content-type"] == "application/pdf"
    assert original.content == data

    display = client.get(
        f"/api/projects/{project_id}/assets/{pages[0]['display_asset_id']}/file"
    )
    assert display.status_code == 200
    assert display.headers["content-type"] == "image/png"

    run = client.get(f"/api/projects/{project_id}/pages/{pages[0]['id']}/ocr").json()
    assert run is not None
    assert run["engine"] == "pdf-text"
    assert run["status"] == "succeeded"
    assert run["stale"] is False
    # Embedded text is exact source data, not a scored OCR prediction.
    assert run["mean_confidence"] is None
    assert "Hello PDF" in run["text"]
    assert run["blocks"]
    assert all(block["confidence"] is None for block in run["blocks"])

    second = client.get(f"/api/projects/{project_id}/pages/{pages[1]['id']}/ocr").json()
    assert second is not None
    assert "Second page body" in second["text"]


def test_image_only_pdf_page_has_no_embedded_text_run(
    client: TestClient, project: dict
) -> None:
    pages = upload_pdf(client, project["id"], "scanned.pdf", make_image_only_pdf())
    assert len(pages) == 1
    assert pages[0]["source_kind"] == "pdf"

    run = client.get(f"/api/projects/{project['id']}/pages/{pages[0]['id']}/ocr").json()
    assert run is None

    # Image-only PDF pages can still be imported alongside regular images.
    image_pages = upload_pages(client, project["id"], ["extra.png"])
    assert image_pages[0]["page_number"] == 2
    assert image_pages[0]["pdf_page_number"] is None


def test_mixed_pdf_extracts_only_text_pages(client: TestClient, project: dict) -> None:
    document = pymupdf.open()
    try:
        text_page = document.new_page(width=595, height=842)
        text_page.insert_text((72, 100), "Typed caption", fontsize=14)
        image_page = document.new_page(width=595, height=842)
        image_page.insert_image(pymupdf.Rect(72, 72, 500, 360), stream=make_png(600, 400))
        data = document.tobytes()
    finally:
        document.close()

    pages = upload_pdf(client, project["id"], "mixed.pdf", data)
    assert [page["pdf_page_number"] for page in pages] == [1, 2]

    first = client.get(f"/api/projects/{project['id']}/pages/{pages[0]['id']}/ocr").json()
    second = client.get(f"/api/projects/{project['id']}/pages/{pages[1]['id']}/ocr").json()
    assert first is not None and "Typed caption" in first["text"]
    assert second is None


def test_mixed_batch_imports_images_and_pdfs_with_unicode_names(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    pdf_name = "အခန်း-၃.pdf"
    image_name = "ဓာတ်ပုံ.png"
    response = client.post(
        f"/api/projects/{project_id}/pages/import",
        files=[
            ("files", (pdf_name, make_pdf(["Unicode batch"]), "application/pdf")),
            ("files", (image_name, make_png(), "image/png")),
        ],
    )
    assert response.status_code == 200, response.text
    pages = response.json()

    assert [page["page_number"] for page in pages] == [1, 2]
    assert [page["source_kind"] for page in pages] == ["pdf", "image"]
    assert pages[0]["original_filename"] == pdf_name
    assert pages[1]["original_filename"] == image_name
    assert pages[0]["pdf_page_number"] == 1
    assert pages[1]["pdf_page_number"] is None
    assert pages[0]["original_asset_id"] != pages[1]["original_asset_id"]


def test_rotate_pdf_page_rerenders_from_original_and_marks_text_stale(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    data = make_pdf(["Rotate me"])
    page = upload_pdf(client, project_id, "rotate.pdf", data)[0]
    original_run = client.get(
        f"/api/projects/{project_id}/pages/{page['id']}/ocr"
    ).json()
    assert original_run["stale"] is False

    rotated = client.post(
        f"/api/projects/{project_id}/pages/{page['id']}/rotate", json={"degrees": 90}
    )
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert body["rotation"] == 90
    assert body["width"] == page["height"]
    assert body["height"] == page["width"]
    assert body["display_asset_id"] != page["display_asset_id"]

    # The embedded text was extracted against the unrotated page.
    stale_run = client.get(
        f"/api/projects/{project_id}/pages/{page['id']}/ocr"
    ).json()
    assert stale_run["id"] == original_run["id"]
    assert stale_run["stale"] is True

    # Rotating back re-renders again; the PDF itself is never rewritten.
    restored = client.post(
        f"/api/projects/{project_id}/pages/{page['id']}/rotate", json={"degrees": 270}
    ).json()
    assert restored["rotation"] == 0
    assert restored["width"] == page["width"]
    assert restored["height"] == page["height"]
    assert restored["display_asset_id"]

    original = client.get(
        f"/api/projects/{project_id}/assets/{page['original_asset_id']}/file"
    )
    assert original.content == data


def test_delete_shared_pdf_source_only_when_last_page_is_removed(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    pages = upload_pdf(client, project_id, "shared.pdf", make_pdf(["One", "Two"]))
    source_id = pages[0]["original_asset_id"]
    source_url = f"/api/projects/{project_id}/assets/{source_id}/file"

    deleted = client.delete(f"/api/projects/{project_id}/pages/{pages[0]['id']}")
    assert deleted.status_code == 200
    assert client.get(source_url).status_code == 200

    remaining = client.get(f"/api/projects/{project_id}/pages").json()
    assert [item["pdf_page_number"] for item in remaining] == [2]
    # Page numbers are renumbered after deletion; the PDF page index is kept.
    assert remaining[0]["page_number"] == 1

    deleted = client.delete(f"/api/projects/{project_id}/pages/{remaining[0]['id']}")
    assert deleted.status_code == 200
    assert client.get(source_url).status_code == 404


def test_encrypted_pdf_is_rejected_without_creating_pages(
    client: TestClient, project: dict, tmp_path: Path
) -> None:
    document = pymupdf.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 100), "Protected", fontsize=14)
        target = tmp_path / "protected.pdf"
        document.save(
            target,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner-secret",
            user_pw="user-secret",
        )
        data = target.read_bytes()
    finally:
        document.close()

    response = client.post(
        f"/api/projects/{project['id']}/pages/import",
        files=[("files", ("protected.pdf", data, "application/pdf"))],
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "pdf_encrypted"
    assert client.get(f"/api/projects/{project['id']}/pages").json() == []


def test_pdf_page_limit_is_enforced(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DOCUREBUILD_PDF_MAX_PAGES", "1")
    get_settings.cache_clear()

    response = client.post(
        f"/api/projects/{project['id']}/pages/import",
        files=[
            ("files", ("long.pdf", make_pdf(["One", "Two"]), "application/pdf")),
        ],
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "pdf_too_many_pages"
    assert client.get(f"/api/projects/{project['id']}/pages").json() == []


def test_pdf_capability_is_reported_honestly(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import pdf as pdf_service

    meta = client.get("/api/meta").json()
    assert meta["capabilities"]["import_pdf"] is True

    monkeypatch.setattr(pdf_service, "pymupdf", None)
    assert client.get("/api/meta").json()["capabilities"]["import_pdf"] is False

    response = client.post(
        f"/api/projects/{project['id']}/pages/import",
        files=[("files", ("book.pdf", b"%PDF-1.7", "application/pdf"))],
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "pdf_unavailable"
