from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import AppError
from app.services import document_export
from app.services.document_export import render_pdf
from tests.conftest import upload_pages


def _open(data: bytes) -> pymupdf.Document:
    assert data.startswith(b"%PDF")
    return pymupdf.open("pdf", data)


def _text(document: pymupdf.Document) -> str:
    # PyMuPDF writes shaped text with non-breaking spaces and line breaks, and
    # the built-in proportional fonts use standard fi/fl/ffi ligature glyphs.
    raw = " ".join(page.get_text() for page in document)
    for ligature, replacement in (
        ("\ufb00", "ff"),
        ("\ufb01", "fi"),
        ("\ufb02", "fl"),
        ("\ufb03", "ffi"),
        ("\ufb04", "ffl"),
    ):
        raw = raw.replace(ligature, replacement)
    return " ".join(raw.replace("\xa0", " ").split())


def _content() -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1, "textAlign": "center"},
                "content": [{"type": "text", "text": "Quantum Mechanics"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "The "},
                    {
                        "type": "text",
                        "text": "Schrödinger",
                        "marks": [{"type": "bold"}],
                    },
                    {"type": "text", "text": " equation and "},
                    {
                        "type": "text",
                        "text": "a link",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {"href": "https://example.com/a"},
                            }
                        ],
                    },
                    {"type": "text", "text": "."},
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "First item"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Second item"}],
                            }
                        ],
                    },
                ],
            },
            {
                "type": "orderedList",
                "attrs": {"start": 3},
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Third item"}],
                            }
                        ],
                    }
                ],
            },
            {
                "type": "blockquote",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Quoted text"}],
                    }
                ],
            },
            {
                "type": "codeBlock",
                "attrs": {"language": "python"},
                "content": [{"type": "text", "text": "print('x')"}],
            },
            {"type": "horizontalRule"},
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableHeader",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Name"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableHeader",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Value"}],
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Alpha"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "attrs": {"textAlign": "right"},
                                        "content": [{"type": "text", "text": "1"}],
                                    }
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }


def test_pdf_export_renders_structure_links_and_metadata(tmp_path: Path) -> None:
    data = render_pdf(_content(), tmp_path, "Quantum Mechanics")
    document = _open(data)

    assert document.page_count == 1
    text = _text(document)
    assert "Quantum Mechanics" in text
    assert "Schrödinger" in text
    assert "First item" in text
    assert "Second item" in text
    assert "Third item" in text
    assert "Quoted text" in text
    assert "print('x')" in text
    assert "Name" in text and "Value" in text
    assert "Alpha" in text

    metadata = document.metadata
    assert metadata["title"] == "Quantum Mechanics"
    assert metadata["author"] == ""
    assert metadata["creator"] == "DocuRebuild"
    assert metadata["producer"] == "DocuRebuild"
    assert metadata["creationDate"] == ""
    assert metadata["modDate"] == ""

    # A link becomes a clickable annotation instead of a dead text run.
    links = document[0].get_links()
    assert any(link.get("uri") == "https://example.com/a" for link in links)
    # A page number is generated chrome, not document text.
    assert f"1 / {document.page_count}" in text


def test_pdf_export_is_reproducible(tmp_path: Path) -> None:
    content = _content()
    first = render_pdf(content, tmp_path, "Quantum Mechanics")
    second = render_pdf(content, tmp_path, "Quantum Mechanics")
    assert first == second


def test_pdf_export_keeps_burmese_glyphs(tmp_path: Path) -> None:
    if document_export._find_myanmar_font() is None:
        pytest.skip("No Unicode Myanmar font is installed on this machine.")
    content = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "မြန်မာ စာအုပ်"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "ကျွန်ုပ်တို့သည် စာရွက်စာတမ်းများကို ပြန်လည်တည်ဆောက်သည်။",
                    }
                ],
            },
        ],
    }
    document = _open(render_pdf(content, tmp_path, "မြန်မာ"))
    text = document[0].get_text()
    assert any("\u1000" <= char <= "\u109f" for char in text)


def test_pdf_export_requires_a_font_for_burmese(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_export, "_find_myanmar_font", lambda: None)
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "မြန်မာ"}],
            }
        ],
    }
    with pytest.raises(AppError) as error:
        render_pdf(content, tmp_path)
    assert error.value.code == "pdf_font_missing"


def test_pdf_export_english_needs_no_myanmar_font(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_export, "_find_myanmar_font", lambda: None)
    data = render_pdf(
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "English only"}],
                }
            ],
        },
        tmp_path,
    )
    assert "English only" in _text(_open(data))


def test_pdf_export_embeds_project_figures(
    client: TestClient, project: dict
) -> None:
    page = upload_pages(client, project["id"], ["figure.png"])[0]
    asset_id = page["display_asset_id"] or page["original_asset_id"]
    src = f"/api/projects/{project['id']}/assets/{asset_id}/file"
    content = {
        "type": "doc",
        "content": [
            {
                "type": "figure",
                "attrs": {
                    "src": src,
                    "alt": "Wave function",
                    "caption": "Wavefunction",
                    "note": "Source: page 2",
                },
            }
        ],
    }
    directory = get_settings().projects_dir / project["id"]
    data = render_pdf(content, directory, project["name"])
    document = _open(data)

    assert document[0].get_images()
    text = _text(document)
    assert "Wavefunction" in text
    assert "Source: page 2" in text
    # The local API path and asset id never leak into the exported file.
    assert asset_id.encode() not in data
    assert b"/api/" not in data


def test_pdf_export_marks_a_missing_figure_instead_of_dropping_it(
    tmp_path: Path,
) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "figure",
                "attrs": {
                    "src": "/api/projects/project-1/assets/"
                    "00000000-0000-0000-0000-000000000000/file",
                    "caption": "Missing figure",
                },
            }
        ],
    }
    text = _text(_open(render_pdf(content, tmp_path)))
    assert "[Figure: Missing figure]" in text


def test_pdf_export_writes_footnotes_as_endnotes(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "First claim"},
                    {
                        "type": "footnote",
                        "attrs": {"id": "fn-a", "text": "First note."},
                    },
                    {"type": "text", "text": " and second claim"},
                    {
                        "type": "footnote",
                        "attrs": {"id": "fn-b", "text": "Second note."},
                    },
                    {"type": "text", "text": "."},
                ],
            }
        ],
    }
    text = _text(_open(render_pdf(content, tmp_path)))
    assert "First claim" in text
    assert "Notes" in text
    assert "First note." in text
    assert "Second note." in text


def test_pdf_export_keeps_equation_latex_source(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "blockMath",
                "attrs": {"id": "eq-a", "latex": "\\frac{a}{b} = c", "numbered": True},
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Inline "},
                    {"type": "inlineMath", "attrs": {"latex": "E = mc^2"}},
                    {"type": "text", "text": " stays exact."},
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "See "},
                    {"type": "equationReference", "attrs": {"targetId": "eq-a"}},
                    {"type": "text", "text": "."},
                ],
            },
        ],
    }
    text = _text(_open(render_pdf(content, tmp_path)))
    assert "\\frac{a}{b} = c" in text
    assert "(1)" in text
    assert "E = mc^2" in text
    assert "Equation (1)" in text


def test_pdf_export_escapes_document_markup(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "<script>alert(1)</script> & <b>literal</b>",
                    }
                ],
            }
        ],
    }
    text = _text(_open(render_pdf(content, tmp_path)))
    assert "<script>alert(1)</script> & <b>literal</b>" in text


def test_export_endpoint_returns_pdf(client: TestClient, project: dict) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "PDF body."}],
            }
        ],
    }
    saved = client.put(
        f"/api/projects/{project['id']}/document",
        json={"content": content, "plain_text": "PDF body."},
    )
    assert saved.status_code == 200, saved.text

    response = client.get(
        f"/api/projects/{project['id']}/document/export",
        params={"format": "pdf"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="Quantum-Mechanics.pdf"' in response.headers[
        "content-disposition"
    ]
    assert response.content.startswith(b"%PDF")
    assert "PDF body." in _text(_open(response.content))

    history = client.get(f"/api/projects/{project['id']}/history").json()
    exported = [
        event for event in history if event.get("event_type") == "document_exported"
    ]
    assert exported
    assert exported[0]["payload"]["format"] == "pdf"
    assert exported[0]["payload"]["byte_size"] == len(response.content)
