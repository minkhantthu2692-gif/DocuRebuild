from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def _rect(width: int = 300, height: int = 600) -> TTGlyphPen:
    pen = TTGlyphPen(None)
    pen.moveTo((40, 0))
    pen.lineTo((40, height))
    pen.lineTo((40 + width, height))
    pen.lineTo((40 + width, 0))
    pen.closePath()
    return pen


def build_font_bytes(
    *,
    family: str = "Docu Test",
    style: str = "Regular",
    weight: int = 400,
    italic: bool = False,
) -> bytes:
    """Build a tiny valid sfnt with the glyphs the export tests need."""
    builder = FontBuilder(1000, isTTF=True)
    glyph_order = [
        ".notdef",
        "space",
        "A",
        "B",
        "H",
        "O",
        "x",
        "one",
        "two",
        "sup2",
        "sub2",
    ]
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(
        {
            32: "space",
            65: "A",
            66: "B",
            72: "H",
            79: "O",
            120: "x",
            49: "one",
            50: "two",
            0x00B2: "sup2",
            0x2082: "sub2",
        }
    )
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    glyphs["space"] = TTGlyphPen(None).glyph()
    for name in glyph_order[2:]:
        glyphs[name] = _rect().glyph()
    builder.setupGlyf(glyphs)
    metrics = {name: (600, 0) for name in glyph_order}
    metrics["space"] = (300, 0)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": family, "styleName": style})
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
        usWeightClass=weight,
        fsType=0,
        fsSelection=(1 if italic else 0) | (32 if style.lower().startswith("bold") else 0),
    )
    builder.setupPost()
    buffer = io.BytesIO()
    builder.save(buffer)
    return buffer.getvalue()


def _woff2(data: bytes) -> bytes:
    """Re-wrap a TTF as WOFF2 so the import conversion path is exercised."""
    pytest.importorskip("brotli")
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(data))
    try:
        font.flavor = "woff2"
        buffer = io.BytesIO()
        font.save(buffer)
        return buffer.getvalue()
    finally:
        font.close()


@pytest.fixture(autouse=True)
def _isolate_system_fonts(monkeypatch, tmp_path):
    """Keep tests independent from the fonts installed on the build machine."""
    import app.services.fonts as font_service

    folder = tmp_path / "system-fonts"
    folder.mkdir()
    monkeypatch.setenv("DOCUREBUILD_SYSTEM_FONT_DIRS", str(folder))
    font_service.clear_system_font_cache()
    try:
        yield folder
    finally:
        font_service.clear_system_font_cache()


def _upload(client: TestClient, data: bytes, name: str = "DocuTest.ttf"):
    return client.post(
        "/api/fonts/import",
        files={"file": (name, data, "font/ttf")},
    )


def test_lists_installed_system_fonts(client: TestClient, _isolate_system_fonts) -> None:
    system_font = _isolate_system_fonts / "DocuSystem.ttf"
    system_font.write_bytes(build_font_bytes(family="Docu System"))

    response = client.get("/api/fonts")
    assert response.status_code == 200, response.text
    payload = response.json()

    names = {family["name"] for family in payload["families"]}
    assert "Docu System" in names
    family = next(entry for entry in payload["families"] if entry["name"] == "Docu System")
    assert family["source"] == "system"
    assert family["available"] is True
    assert family["faces"][0]["source"] == "system"
    assert family["faces"][0]["id"] is None
    assert payload["imported_count"] == 0
    assert payload["system_count"] == 1


def test_import_stores_deduplicates_and_serves_the_font(client: TestClient) -> None:
    data = build_font_bytes()

    first = _upload(client, data)
    assert first.status_code == 201, first.text
    face = first.json()
    assert face["family"] == "Docu Test"
    assert face["source"] == "imported"
    assert face["weight"] == 400
    assert face["italic"] is False
    assert face["format"] == "ttf"

    duplicate = _upload(client, data)
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["id"] == face["id"]

    listing = client.get("/api/fonts").json()
    assert listing["imported_count"] == 1
    family = next(entry for entry in listing["families"] if entry["name"] == "Docu Test")
    assert family["source"] == "imported"
    assert len(family["faces"]) == 1

    served = client.get(f"/api/fonts/{face['id']}/file")
    assert served.status_code == 200
    assert served.content == data
    assert served.headers["content-type"].startswith("font/ttf")


def test_import_converts_woff2_to_a_standard_font(client: TestClient) -> None:
    data = _woff2(build_font_bytes(family="Docu Web"))

    response = _upload(client, data, "DocuWeb.woff2")
    assert response.status_code == 201, response.text
    face = response.json()
    assert face["family"] == "Docu Web"
    assert face["format"] in {"ttf", "otf"}

    served = client.get(f"/api/fonts/{face['id']}/file")
    assert served.status_code == 200
    # The stored file is a plain sfnt, not the web-font container.
    assert served.content[:4] not in {b"wOFF", b"wOF2"}


def test_import_rejects_a_file_that_is_not_a_font(client: TestClient) -> None:
    response = _upload(client, b"not a font at all", "fake.ttf")
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] in {"font_invalid", "font_unsupported"}

    listing = client.get("/api/fonts").json()
    assert listing["imported_count"] == 0


def test_delete_font_removes_the_face_and_its_file(client: TestClient) -> None:
    face = _upload(client, build_font_bytes()).json()

    removed = client.delete(f"/api/fonts/{face['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/fonts/{face['id']}/file").status_code == 404
    assert client.delete(f"/api/fonts/{face['id']}").status_code == 404

    listing = client.get("/api/fonts").json()
    assert listing["imported_count"] == 0
    assert all(entry["name"] != "Docu Test" for entry in listing["families"])


def _document_with_typography() -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Energy "},
                    {
                        "type": "text",
                        "text": "x2",
                        "marks": [{"type": "superscript"}],
                    },
                    {"type": "text", "text": " and water H"},
                    {
                        "type": "text",
                        "text": "2",
                        "marks": [{"type": "subscript"}],
                    },
                    {"type": "text", "text": "O "},
                    {
                        "type": "text",
                        "text": "AB",
                        "marks": [
                            {
                                "type": "textStyle",
                                "attrs": {"fontFamily": "Docu Test"},
                            }
                        ],
                    },
                ],
            }
        ],
    }


def test_docx_export_embeds_the_imported_font(
    client: TestClient, project: dict
) -> None:
    face = _upload(client, build_font_bytes()).json()
    content = _document_with_typography()
    saved = client.put(
        f"/api/projects/{project['id']}/document",
        json={"content": content, "plain_text": "Energy x2 and water H2O AB"},
    )
    assert saved.status_code == 200, saved.text

    response = client.get(
        f"/api/projects/{project['id']}/document/export",
        params={"format": "docx"},
    )
    assert response.status_code == 200, response.text

    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        names = package.namelist()
        embedded = [name for name in names if name.startswith("word/fonts/")]
        assert embedded, names
        font_table = package.read("word/fontTable.xml").decode("utf-8")
        settings = package.read("word/settings.xml").decode("utf-8")
        document_xml = package.read("word/document.xml").decode("utf-8")

    assert "Docu Test" in font_table
    assert "w:embedTrueTypeFonts" in settings
    # The run keeps the family and the scientific marks.
    assert "Docu Test" in document_xml
    assert "superscript" in document_xml
    assert "subscript" in document_xml
    assert face["id"]  # imported id is not written into the package
    assert face["id"] not in document_xml


def test_pdf_export_embeds_the_imported_font(
    client: TestClient, project: dict
) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    _upload(client, build_font_bytes())
    content = _document_with_typography()
    saved = client.put(
        f"/api/projects/{project['id']}/document",
        json={"content": content, "plain_text": "Energy x2 and water H2O AB"},
    )
    assert saved.status_code == 200, saved.text

    response = client.get(
        f"/api/projects/{project['id']}/document/export",
        params={"format": "pdf"},
    )
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF")

    document = pymupdf.open(stream=response.content, filetype="pdf")
    try:
        page_fonts = {
            entry[3].split("+")[-1] for entry in document.get_page_fonts(0)
        }
        text = document[0].get_text()
    finally:
        document.close()

    assert any("Docu" in name for name in page_fonts), page_fonts
    assert "Energy" in text
    assert "water" in text


def test_missing_font_name_does_not_break_the_export(
    client: TestClient, project: dict
) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Unknown typeface",
                        "marks": [
                            {
                                "type": "textStyle",
                                "attrs": {"fontFamily": "Not Installed Anywhere"},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    saved = client.put(
        f"/api/projects/{project['id']}/document",
        json={"content": content, "plain_text": "Unknown typeface"},
    )
    assert saved.status_code == 200, saved.text

    for export_format in ("docx", "pdf"):
        response = client.get(
            f"/api/projects/{project['id']}/document/export",
            params={"format": export_format},
        )
        assert response.status_code == 200, response.text
        assert len(response.content) > 0
