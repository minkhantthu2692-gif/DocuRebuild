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


def test_extract_text_attaches_real_word_boxes_to_blocks() -> None:
    from app.services import pdf

    class FakePage:
        rect = type("Rect", (), {"height": 800})()

        def get_text(self, kind: str, sort: bool = False):
            if kind == "dict":
                return {
                    "blocks": [
                        {
                            "type": 0,
                            "bbox": (0, 0, 200, 20),
                            "lines": [
                                {
                                    "spans": [
                                        {
                                            "text": "Name Value",
                                            "size": 10,
                                            "bbox": (0, 0, 200, 10),
                                        }
                                    ]
                                }
                            ],
                        }
                    ]
                }
            return [
                (0, 0, 40, 10, "Name", 0, 0, 0),
                (50, 0, 90, 10, "Value", 0, 0, 1),
            ]

    class FakeDocument:
        def load_page(self, index: int):
            return FakePage()

    text, blocks = pdf.extract_text(FakeDocument(), 0, 2.0)

    assert text == "Name Value"
    # Word boxes come from the PDF itself, not from estimated character widths.
    assert blocks[0]["words"] == [
        {
            "text": "Name",
            "confidence": None,
            "x": 0,
            "y": 0,
            "width": 80,
            "height": 20,
            "line": 0,
        },
        {
            "text": "Value",
            "confidence": None,
            "x": 100,
            "y": 0,
            "width": 80,
            "height": 20,
            "line": 0,
        },
    ]


def test_image_regions_convert_pdf_boxes_to_rendered_pixels() -> None:
    from app.services import pdf

    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        page.insert_image(pymupdf.Rect(100, 200, 300, 350), stream=make_png(40, 30))

        # A 600 pt wide page rendered 1200 px wide doubles every coordinate.
        regions = pdf.image_regions(document, 0, 1200)
        assert len(regions) == 1
        assert regions[0] == {"x": 200.0, "y": 400.0, "width": 400.0, "height": 300.0}

        # A page-level /Rotate is applied so the box stays aligned with the
        # pixmap the workspace displays.
        page.set_rotation(90)
        rotated = pdf.image_regions(document, 0, 1600)
        assert len(rotated) == 1
        assert rotated[0] == {"x": 900.0, "y": 200.0, "width": 300.0, "height": 400.0}
    finally:
        document.close()


def test_image_regions_returns_nothing_for_an_unreadable_page() -> None:
    from app.services import pdf

    class FakeDocument:
        def load_page(self, index: int):
            raise RuntimeError("cannot read")

    assert pdf.image_regions(FakeDocument(), 0, 1200) == []


def test_table_lines_reads_strokes_thin_fills_and_stroked_rectangles() -> None:
    from app.services import pdf

    document = pymupdf.open()
    try:
        page = document.new_page(width=400, height=300)
        page.draw_line((50, 50), (350, 50), color=(0, 0, 0), width=0.8)
        page.draw_rect(
            pymupdf.Rect(50, 100, 350, 101), color=None, fill=(0, 0, 0)
        )
        page.draw_rect(
            pymupdf.Rect(50, 150, 350, 250), color=(0, 0, 0), width=0.8
        )
        # A diagonal cannot describe a cell edge and must be ignored.
        page.draw_line((50, 50), (100, 90), color=(0, 0, 0), width=0.8)

        # A 400 pt wide page rendered 800 px wide doubles every coordinate.
        horizontals, verticals = pdf.table_lines(document, 0, 800)
    finally:
        document.close()

    assert sorted(horizontals) == [
        (100.0, 100.0, 700.0),
        (201.0, 100.0, 700.0),
        (300.0, 100.0, 700.0),
        (500.0, 100.0, 700.0),
    ]
    # The stroked rectangle contributes its four edges.
    assert sorted(verticals) == [
        (100.0, 300.0, 500.0),
        (700.0, 300.0, 500.0),
    ]


def test_table_lines_returns_nothing_for_an_unreadable_page() -> None:
    from app.services import pdf

    class FakeDocument:
        def load_page(self, index: int):
            raise RuntimeError("cannot read")

    assert pdf.table_lines(FakeDocument(), 0, 1200) == ([], [])


def test_drawing_regions_find_vector_artwork_but_not_rules() -> None:
    from app.services import pdf

    document = pymupdf.open()
    try:
        page = document.new_page(width=400, height=400)
        # A chart without a frame: axis rules, two filled bars and a trend line.
        page.draw_line((50, 50), (50, 250), color=(0, 0, 0), width=0.8)
        page.draw_line((50, 250), (350, 250), color=(0, 0, 0), width=0.8)
        page.draw_rect(
            pymupdf.Rect(80, 200, 120, 250), color=None, fill=(0.2, 0.4, 0.8)
        )
        page.draw_rect(
            pymupdf.Rect(140, 150, 180, 250), color=None, fill=(0.2, 0.4, 0.8)
        )
        page.draw_line((80, 210), (180, 160), color=(0.8, 0.1, 0.1), width=1.2)
        # A drawn table is rules only, so it is not artwork.
        for y in (300, 330, 360):
            page.draw_line((50, y), (250, y), color=(0, 0, 0), width=0.8)
        for x in (50, 150, 250):
            page.draw_line((x, 300), (x, 360), color=(0, 0, 0), width=0.8)
        # A lone filled rectangle is shading, not a drawing.
        page.draw_rect(
            pymupdf.Rect(300, 300, 380, 310), color=None, fill=(0.9, 0.9, 0.9)
        )
        # An unfilled page frame is a border, not a drawing.
        page.draw_rect(pymupdf.Rect(10, 10, 390, 390), color=(0, 0, 0), width=1.0)

        # A 400 pt wide page rendered 800 px wide doubles every coordinate.
        regions = pdf.drawing_regions(document, 0, 800)
    finally:
        document.close()

    assert regions == [
        {"x": 160.0, "y": 300.0, "width": 200.0, "height": 200.0}
    ]


def test_drawing_regions_join_parts_that_belong_to_one_drawing() -> None:
    from app.services import pdf

    document = pymupdf.open()
    try:
        page = document.new_page(width=400, height=400)
        # Two shapes with a small gap are one drawing, not two suggestions.
        page.draw_rect(
            pymupdf.Rect(100, 100, 140, 140), color=None, fill=(0.2, 0.4, 0.8)
        )
        page.draw_rect(
            pymupdf.Rect(146, 100, 186, 140), color=None, fill=(0.2, 0.4, 0.8)
        )
        # A third shape far away stays its own region, but a lone filled
        # rectangle is rejected, so only the joined pair is returned.
        page.draw_rect(
            pymupdf.Rect(300, 300, 340, 340), color=None, fill=(0.2, 0.4, 0.8)
        )

        regions = pdf.drawing_regions(document, 0, 400)
    finally:
        document.close()

    assert regions == [{"x": 100.0, "y": 100.0, "width": 86.0, "height": 40.0}]


def test_drawing_regions_returns_nothing_for_an_unreadable_page() -> None:
    from app.services import pdf

    class FakeDocument:
        def load_page(self, index: int):
            raise RuntimeError("cannot read")

    assert pdf.drawing_regions(FakeDocument(), 0, 1200) == []


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
