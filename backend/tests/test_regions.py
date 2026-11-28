from __future__ import annotations

import io
import time

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from tests.conftest import make_png, upload_pages


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


def _figure_pdf(
    *,
    caption: str | None = None,
    background: bool = False,
    logo: bool = False,
) -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        if background:
            page.insert_image(
                pymupdf.Rect(0, 0, 600, 800), stream=make_png(300, 400)
            )
        elif logo:
            page.insert_image(pymupdf.Rect(72, 40, 92, 50), stream=make_png(20, 10))
        else:
            page.insert_image(
                pymupdf.Rect(100, 200, 400, 400), stream=make_png(300, 200)
            )
        page.insert_text((72, 100), "Body text on the same page.", fontsize=12)
        if caption:
            page.insert_text((100, 460), caption, fontsize=12)
        return document.tobytes()
    finally:
        document.close()


def _vector_figure_pdf(*, caption: str | None = None, image: bool = False) -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        black = (0, 0, 0)
        page.insert_text((72, 80), "Body text above the chart.", fontsize=12)
        if image:
            page.insert_image(
                pymupdf.Rect(100, 360, 300, 500), stream=make_png(200, 140)
            )
            # A shaded backing behind the image must not become a second figure.
            page.draw_rect(
                pymupdf.Rect(100, 360, 300, 500), color=None, fill=(0.9, 0.95, 1.0)
            )
            page.draw_rect(
                pymupdf.Rect(104, 364, 296, 496), color=None, fill=(0.85, 0.9, 1.0)
            )
        else:
            # A chart without a frame: axis rules, filled bars and a trend line.
            page.draw_line((80, 500), (520, 500), color=black, width=0.8)
            page.draw_line((80, 300), (80, 500), color=black, width=0.8)
            page.draw_rect(
                pymupdf.Rect(120, 420, 180, 500), color=None, fill=(0.2, 0.4, 0.8)
            )
            page.draw_rect(
                pymupdf.Rect(240, 360, 300, 500), color=None, fill=(0.2, 0.4, 0.8)
            )
            page.draw_line(
                (120, 440), (300, 380), color=(0.8, 0.1, 0.1), width=1.2
            )
        # A drawn table further down is rules only, so it is never a figure.
        for y in (620, 660, 700):
            page.draw_line((80, y), (400, y), color=black, width=0.8)
        for x in (80, 240, 400):
            page.draw_line((x, 620), (x, 700), color=black, width=0.8)
        if caption:
            page.insert_text((120, 540), caption, fontsize=12)
        return document.tobytes()
    finally:
        document.close()


def _upload_pdf(
    client: TestClient, project_id: str, name: str, data: bytes
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/pages/import",
        files=[("files", (name, data, "application/pdf"))],
    )
    assert response.status_code == 200, response.text
    return response.json()[0]


def _page_artwork_png(*, text_only: bool = False, caption: str | None = None) -> bytes:
    image = Image.new("RGB", (1200, 800), (252, 252, 252))
    draw = ImageDraw.Draw(image)
    # Body text the OCR run locates, so its ink is never treated as artwork.
    for y in range(100, 180, 26):
        draw.rectangle((100, y, 520, y + 10), fill=(30, 30, 30))
    if not text_only:
        # A chart made of separate parts: rules, filled bars and a trend line.
        draw.line((700, 560, 1060, 560), fill=(20, 20, 20), width=2)
        draw.line((700, 260, 700, 560), fill=(20, 20, 20), width=2)
        for x, top in ((740, 420), (800, 340), (860, 260)):
            draw.rectangle((x, top, x + 34, 560), fill=(40, 80, 160))
        draw.line((700, 440, 1060, 300), fill=(160, 40, 40), width=3)
    if caption:
        draw.rectangle((740, 620, 1040, 634), fill=(30, 30, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _opaque_pdf(*, chart: bool = True) -> bytes:
    """A PDF whose page is one full-page raster image and no vector paths.

    The image fills the page, so the embedded-image filter treats it as a
    background and there are no drawings to read; the rendered page is the only
    signal left for an opaque drawing.
    """
    image = Image.new("RGB", (1200, 800), (252, 252, 252))
    draw = ImageDraw.Draw(image)
    for y in range(100, 180, 26):
        draw.rectangle((100, y, 520, y + 10), fill=(30, 30, 30))
    if chart:
        draw.line((700, 560, 1060, 560), fill=(20, 20, 20), width=2)
        draw.line((700, 260, 700, 560), fill=(20, 20, 20), width=2)
        for x, top in ((740, 420), (800, 340), (860, 260)):
            draw.rectangle((x, top, x + 34, 560), fill=(40, 80, 160))
        draw.line((700, 440, 1060, 300), fill=(160, 40, 40), width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = buffer.getvalue()
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=400)
        page.insert_image(pymupdf.Rect(0, 0, 600, 400), stream=data)
        return document.tobytes()
    finally:
        document.close()


def _upload_png(
    client: TestClient, project_id: str, name: str, data: bytes
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/pages/import",
        files=[("files", (name, data, "image/png"))],
    )
    assert response.status_code == 200, response.text
    return response.json()[0]


def _figure_proposals(
    client: TestClient, project_id: str, page_id: str
) -> tuple[dict, list[dict]]:
    response = client.get(
        f"/api/projects/{project_id}/pages/{page_id}/region-proposals"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body, [
        proposal for proposal in body["proposals"] if proposal["kind"] == "figure"
    ]


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


def test_region_proposals_become_stale_after_a_source_edit(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr, "_perform_ocr", lambda *args, **kwargs: _fake_result(LAYOUT_BLOCKS)
    )
    page = upload_pages(client, project["id"], ["proposal-edited.png"])[0]
    _run_ocr(client, project["id"], page["id"])

    # A geometry edit rebuilds the display asset, so the stored OCR layout no
    # longer describes the current source. Proposals must be withheld even
    # though a successful run exists: a persisted list would otherwise point at
    # the old render.
    edited = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}/edits",
        json={
            "edits": {
                "geometry": [
                    {
                        "type": "crop",
                        "rect": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                    }
                ]
            }
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["display_asset_id"] != page["display_asset_id"]

    body = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    ).json()
    assert body["status"] == "ocr_stale"
    assert body["proposals"] == []


def test_region_proposals_follow_a_new_ocr_run(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    # The fake engine reads the current block set, so two runs can return
    # different layouts from the same page.
    blocks = {"current": LAYOUT_BLOCKS}
    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr, "_perform_ocr", lambda *args, **kwargs: _fake_result(blocks["current"])
    )
    page = upload_pages(client, project["id"], ["proposal-rerun.png"])[0]

    first = _run_ocr(client, project["id"], page["id"])
    first_body = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    ).json()
    assert first_body["ocr_run_id"] == first["id"]
    assert {proposal["kind"] for proposal in first_body["proposals"]} == {
        "figure",
        "table",
        "equation",
    }

    # A second run with a different layout must replace the derived proposals.
    # Nothing from the first run is cached or served as current, which is the
    # invariant a persisted design has to keep when the OCR run id changes.
    blocks["current"] = [_block(1, "paragraph", "Only prose now.", 100, 100, 500, 80)]
    second = _run_ocr(client, project["id"], page["id"])
    assert second["id"] != first["id"]

    second_body = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/region-proposals"
    ).json()
    assert second_body["ocr_run_id"] == second["id"]
    assert second_body["proposals"] == []


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


def test_pdf_image_region_proposes_an_uncaptioned_figure(
    client: TestClient, project: dict
) -> None:
    page = _upload_pdf(client, project["id"], "figure.pdf", _figure_pdf())
    body, figures = _figure_proposals(client, project["id"], page["id"])

    assert body["status"] == "ready"
    assert len(figures) == 1
    figure = figures[0]
    assert figure["reason"] == "pdf_image_region"
    assert figure["confidence"] == "medium"
    assert figure["caption"] == ""
    assert figure["block_ids"] == []
    # The box is the image's own placement, padded and clamped like any other
    # proposal, not the empty band a caption heuristic would estimate.
    scale = body["page_width"] / 600
    assert abs(figure["x"] - round(100 * scale)) <= 20
    assert abs(figure["y"] - round(200 * scale)) <= 20
    assert abs(figure["width"] - round(300 * scale)) <= 40
    assert abs(figure["height"] - round(200 * scale)) <= 40


def test_pdf_image_region_merges_a_matching_caption(
    client: TestClient, project: dict
) -> None:
    caption = "Figure 1. Measured mass spectrum of the sample"
    page = _upload_pdf(
        client, project["id"], "captioned-figure.pdf", _figure_pdf(caption=caption)
    )
    body, figures = _figure_proposals(client, project["id"], page["id"])

    assert len(figures) == 1
    # One proposal instead of a close image box plus an estimated caption band.
    assert figures[0]["reason"] == "pdf_image_region"
    assert figures[0]["caption"] == caption
    assert len(figures[0]["block_ids"]) == 1
    assert all(
        proposal["reason"] != "figure_caption_gap" for proposal in body["proposals"]
    )


def test_pdf_full_page_background_is_not_a_figure(
    client: TestClient, project: dict
) -> None:
    page = _upload_pdf(
        client, project["id"], "scanned.pdf", _figure_pdf(background=True)
    )
    body, figures = _figure_proposals(client, project["id"], page["id"])

    assert body["status"] == "ready"
    assert figures == []


def test_pdf_small_logo_is_not_a_figure(client: TestClient, project: dict) -> None:
    page = _upload_pdf(client, project["id"], "logo.pdf", _figure_pdf(logo=True))
    _, figures = _figure_proposals(client, project["id"], page["id"])

    assert figures == []


def test_pdf_image_regions_are_not_proposed_after_a_page_change(
    client: TestClient, project: dict
) -> None:
    page = _upload_pdf(client, project["id"], "rotated.pdf", _figure_pdf())
    rotated = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/rotate",
        json={"degrees": 90},
    )
    assert rotated.status_code == 200, rotated.text

    body, figures = _figure_proposals(client, project["id"], page["id"])
    # The image boxes describe the unrotated render, so they are withheld until
    # the page is processed again rather than displayed in the wrong place.
    assert body["status"] == "ocr_stale"
    assert figures == []


def test_pdf_drawing_region_proposes_vector_artwork(
    client: TestClient, project: dict
) -> None:
    page = _upload_pdf(client, project["id"], "chart.pdf", _vector_figure_pdf())
    body, figures = _figure_proposals(client, project["id"], page["id"])

    assert body["status"] == "ready"
    # The chart is the only proposal: the drawn table below is rules only.
    assert len(body["proposals"]) == 1
    figure = figures[0]
    assert figure["reason"] == "pdf_drawing_region"
    assert figure["confidence"] == "medium"
    assert figure["caption"] == ""
    scale = body["page_width"] / 600
    assert abs(figure["x"] - round(120 * scale)) <= 20
    assert abs(figure["y"] - round(360 * scale)) <= 20
    assert abs(figure["width"] - round(180 * scale)) <= 40
    assert abs(figure["height"] - round(140 * scale)) <= 40


def test_pdf_drawing_region_attaches_a_matching_caption(
    client: TestClient, project: dict
) -> None:
    caption = "Figure 3. Measured response over time"
    page = _upload_pdf(
        client,
        project["id"],
        "captioned-chart.pdf",
        _vector_figure_pdf(caption=caption),
    )
    body, figures = _figure_proposals(client, project["id"], page["id"])

    assert len(figures) == 1
    # The drawing box wins over the estimated caption band, and the caption is
    # moved onto it instead of being offered as a second region.
    assert figures[0]["reason"] == "pdf_drawing_region"
    assert figures[0]["caption"] == caption
    assert len(figures[0]["block_ids"]) == 1
    assert all(
        proposal["reason"] != "figure_caption_gap" for proposal in body["proposals"]
    )


def test_pdf_shaded_backing_behind_an_image_is_not_a_second_figure(
    client: TestClient, project: dict
) -> None:
    page = _upload_pdf(
        client, project["id"], "shaded-image.pdf", _vector_figure_pdf(image=True)
    )
    _, figures = _figure_proposals(client, project["id"], page["id"])

    assert len(figures) == 1
    assert figures[0]["reason"] == "pdf_image_region"


def test_drawing_figures_skip_areas_other_signals_already_cover() -> None:
    from app.services import regions

    drawing = {"x": 100.0, "y": 100.0, "width": 200.0, "height": 100.0}
    image = {"x": 100.0, "y": 100.0, "width": 200.0, "height": 100.0}
    table = {"x": 50.0, "y": 50.0, "width": 400.0, "height": 300.0}
    aside = {"x": 500.0, "y": 500.0, "width": 100.0, "height": 60.0}
    beside = {"x": 320.0, "y": 100.0, "width": 100.0, "height": 100.0}

    # A drawing on top of an image or inside a table is already covered.
    assert regions._drawing_figures([drawing], [image], []) == []
    assert regions._drawing_figures([drawing], [], [table]) == []
    # A drawing next to another region is its own suggestion.
    assert regions._drawing_figures([aside], [image], [table]) == [aside]
    assert regions._drawing_figures([beside], [image], []) == [beside]


def test_page_artwork_region_proposes_ink_the_ocr_text_does_not_explain(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr,
        "_perform_ocr",
        lambda *args, **kwargs: _fake_result(
            [_block(1, "paragraph", "Body text.", 90, 90, 450, 100)]
        ),
    )
    page = _upload_png(
        client, project["id"], "photographed-page.png", _page_artwork_png()
    )
    _run_ocr(client, project["id"], page["id"])

    body, figures = _figure_proposals(client, project["id"], page["id"])

    assert body["status"] == "ready"
    assert len(body["proposals"]) == 1
    figure = figures[0]
    # Ink outside every OCR block is the only local signal on a raster page, so
    # the region is offered for review with a low confidence and no caption.
    assert figure["reason"] == "page_artwork_region"
    assert figure["confidence"] == "low"
    assert figure["caption"] == ""
    assert figure["block_ids"] == []
    assert abs(figure["x"] - 700) <= 30
    assert abs(figure["y"] - 260) <= 30
    assert abs(figure["x"] + figure["width"] - 1060) <= 40
    assert abs(figure["y"] + figure["height"] - 560) <= 40


def test_page_artwork_region_attaches_a_caption_below_the_drawing(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    caption = "Figure 7. Measured response on paper"
    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr,
        "_perform_ocr",
        lambda *args, **kwargs: _fake_result(
            [
                _block(1, "paragraph", "Body text.", 90, 90, 450, 100),
                _block(2, "caption", caption, 740, 610, 300, 40),
            ]
        ),
    )
    page = _upload_png(
        client,
        project["id"],
        "captioned-photo.png",
        _page_artwork_png(caption=caption),
    )
    _run_ocr(client, project["id"], page["id"])

    body, figures = _figure_proposals(client, project["id"], page["id"])

    assert len(figures) == 1
    assert figures[0]["reason"] == "page_artwork_region"
    assert figures[0]["caption"] == caption
    assert len(figures[0]["block_ids"]) == 1
    assert all(
        proposal["reason"] != "figure_caption_gap" for proposal in body["proposals"]
    )


def test_page_artwork_region_ignores_text_the_ocr_layout_explains(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr,
        "_perform_ocr",
        lambda *args, **kwargs: _fake_result(
            [_block(1, "paragraph", "Body text.", 90, 90, 450, 100)]
        ),
    )
    page = _upload_png(
        client, project["id"], "text-page.png", _page_artwork_png(text_only=True)
    )
    _run_ocr(client, project["id"], page["id"])

    _, figures = _figure_proposals(client, project["id"], page["id"])

    assert figures == []


def test_opaque_pdf_uses_the_rendered_page_for_figure_proposals(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr,
        "_perform_ocr",
        lambda *args, **kwargs: _fake_result(
            [_block(1, "paragraph", "Body text.", 90, 90, 450, 100)]
        ),
    )
    page = _upload_pdf(client, project["id"], "opaque.pdf", _opaque_pdf())
    _run_ocr(client, project["id"], page["id"])

    body, figures = _figure_proposals(client, project["id"], page["id"])

    assert body["status"] == "ready"
    # The page's only content is a full-page raster image, so the embedded-image
    # filter rejects it as a background and there are no vector rules. The
    # rendered page still exposes the chart's ink, offered for review at low
    # confidence.
    assert len(figures) == 1
    figure = figures[0]
    assert figure["reason"] == "page_artwork_region"
    assert figure["confidence"] == "low"
    assert figure["caption"] == ""
    # The 1200x800 source image fills the 600x400-point page, so its pixels are
    # scaled by the render DPI before the box is measured.
    scale_x = page["width"] / 1200
    scale_y = page["height"] / 800
    assert abs(figure["x"] - 700 * scale_x) <= 30
    assert abs(figure["y"] - 260 * scale_y) <= 30
    assert abs(figure["x"] + figure["width"] - 1060 * scale_x) <= 40
    assert abs(figure["y"] + figure["height"] - 560 * scale_y) <= 40


def test_opaque_pdf_without_a_drawing_proposes_no_figure(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr,
        "_perform_ocr",
        lambda *args, **kwargs: _fake_result(
            [_block(1, "paragraph", "Body text.", 90, 90, 450, 100)]
        ),
    )
    page = _upload_pdf(
        client, project["id"], "opaque-text.pdf", _opaque_pdf(chart=False)
    )
    _run_ocr(client, project["id"], page["id"])

    _, figures = _figure_proposals(client, project["id"], page["id"])

    assert figures == []
