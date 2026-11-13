from __future__ import annotations

import io
import zipfile
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient
from lxml import etree

from app.core.config import get_settings
from app.services.document_export import render_docx
from tests.conftest import upload_pages


def _open(data: bytes) -> Document:
    return Document(io.BytesIO(data))


def _body_xml(document: Document) -> str:
    return document.element.body.xml


def _paragraph_texts(document: Document) -> list[str]:
    return [paragraph.text for paragraph in document.paragraphs]


def _content() -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
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
                    {"type": "text", "text": " equation."},
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
                                "content": [{"type": "text", "text": "First"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Second"}],
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
                                "content": [{"type": "text", "text": "Third"}],
                            }
                        ],
                    }
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Docs",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {"href": "https://example.com/a"},
                            }
                        ],
                    }
                ],
            },
        ],
    }


def test_docx_export_keeps_structure_and_formatting(tmp_path: Path) -> None:
    data = render_docx(_content(), tmp_path, "Quantum Mechanics")
    assert data[:2] == b"PK"

    document = _open(data)
    texts = _paragraph_texts(document)
    assert "Quantum Mechanics" in texts
    assert "• First" in texts
    assert "• Second" in texts
    assert "3. Third" in texts

    body = _body_xml(document)
    assert "Heading1" in body or "Heading 1" in body
    # Lists keep visible markers and nested indentation.
    assert "w:ind" in body

    hyperlink = next(
        rel
        for rel in document.part.rels.values()
        if rel.reltype.endswith("/hyperlink")
    )
    assert hyperlink.target_ref == "https://example.com/a"
    assert "w:hyperlink" in body
    # The local machine's identity is not written into the file.
    assert document.core_properties.author == ""
    assert document.core_properties.title == "Quantum Mechanics"


def test_docx_export_writes_native_equations(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "blockMath",
                "attrs": {"latex": r"\frac{a}{b} = \sum_{i=1}^{n} x_i^2", "numbered": True},
            },
            {"type": "blockMath", "attrs": {"latex": "c = d"}},
            {
                "type": "blockMath",
                "attrs": {"latex": "e = f", "numbered": True},
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Inline "},
                    {"type": "inlineMath", "attrs": {"latex": "E = mc^2"}},
                    {"type": "text", "text": " stays editable."},
                ],
            },
        ],
    }
    document = _open(render_docx(content, tmp_path))
    body = _body_xml(document)
    assert body.count("<m:oMath>") == 4
    assert "m:f" in body and "m:nary" in body

    texts = _paragraph_texts(document)
    assert any("(1)" in text for text in texts)
    assert any("(2)" in text for text in texts)
    # The number is a label next to the equation, never part of its source.
    assert all("a = b (1)" not in text for text in texts)


def test_docx_export_falls_back_to_latex_when_conversion_fails(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [{"type": "blockMath", "attrs": {"latex": r"\frac{"}}],
    }
    document = _open(render_docx(content, tmp_path))
    assert "\\frac{" in _paragraph_texts(document)


def test_docx_export_numbers_figures_in_document_order(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "figure",
                "attrs": {"caption": "First", "numbered": True},
            },
            {"type": "figure", "attrs": {"caption": "Second"}},
            {
                "type": "figure",
                "attrs": {"caption": "Third", "numbered": True},
            },
        ],
    }
    document = _open(render_docx(content, tmp_path))
    texts = _paragraph_texts(document)
    assert "[Figure 1: First]" in texts
    assert "[Figure: Second]" in texts
    assert "[Figure 2: Third]" in texts


def test_docx_export_resolves_figure_references(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {"type": "figure", "attrs": {"id": "fig-a", "caption": "First", "numbered": True}},
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "See "},
                    {"type": "figureReference", "attrs": {"targetId": "fig-a"}},
                    {"type": "text", "text": " and "},
                    {"type": "figureReference", "attrs": {"targetId": "gone"}},
                    {"type": "text", "text": "."},
                ],
            },
            {"type": "figure", "attrs": {"id": "fig-b", "caption": "Second", "numbered": True}},
        ],
    }
    document = _open(render_docx(content, tmp_path))
    texts = _paragraph_texts(document)
    assert "See Figure 1 and Figure (missing)." in texts
    # A reference never writes a placeholder byte into the Word text.
    assert all("\x00" not in text for text in texts)


def test_docx_export_resolves_equation_references(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {"type": "blockMath", "attrs": {"id": "eq-a", "latex": "a = b", "numbered": True}},
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "From "},
                    {"type": "equationReference", "attrs": {"targetId": "eq-b"}},
                    {"type": "text", "text": " and "},
                    {"type": "equationReference", "attrs": {"targetId": "eq-a"}},
                    {"type": "text", "text": "."},
                ],
            },
            {"type": "blockMath", "attrs": {"id": "eq-b", "latex": "c = d", "numbered": True}},
        ],
    }
    document = _open(render_docx(content, tmp_path))
    texts = _paragraph_texts(document)
    assert "From Equation (2) and Equation (1)." in texts
    assert all("\x00" not in text for text in texts)


def test_docx_export_embeds_project_figures(
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
                    "caption": "Figure 1. Wavefunction",
                    "note": "Source: page 2",
                },
            }
        ],
    }
    directory = get_settings().projects_dir / project["id"]
    document = _open(render_docx(content, directory, project["name"]))

    assert len(document.inline_shapes) == 1
    shape = document.inline_shapes[0]
    assert shape.width <= 6 * 914400  # 6 inches in EMU
    assert shape._inline.docPr.get("descr") == "Wave function"

    texts = _paragraph_texts(document)
    assert "Figure 1. Wavefunction" in texts
    assert "Source: page 2" in texts
    # The local API path never leaks into the exported file.
    assert asset_id not in _body_xml(document)


def test_docx_export_marks_a_missing_figure_instead_of_dropping_it(
    client: TestClient, project: dict
) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    src = f"/api/projects/{project['id']}/assets/{missing}/file"
    content = {
        "type": "doc",
        "content": [
            {
                "type": "figure",
                "attrs": {"src": src, "caption": "Figure 2. Missing"},
            }
        ],
    }
    directory = get_settings().projects_dir / project["id"]
    document = _open(render_docx(content, directory))
    assert "[Figure: Figure 2. Missing]" in _paragraph_texts(document)
    assert len(document.inline_shapes) == 0


def test_docx_export_merges_table_cells(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableHeader",
                                "attrs": {"colspan": 2, "rowspan": 1},
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Merged"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableCell",
                                "attrs": {"colspan": 1, "rowspan": 2},
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Side"}],
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
                                "attrs": {"colspan": 1, "rowspan": 1},
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "A"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableCell",
                                "attrs": {"colspan": 1, "rowspan": 1},
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "B"}],
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }
    document = _open(render_docx(content, tmp_path))
    table = document.tables[0]
    assert len(table.rows) == 2
    assert len(table.columns) == 3
    # The header spans both top columns and the side cell spans both rows.
    assert table.cell(0, 0)._tc is table.cell(0, 1)._tc
    assert table.cell(0, 2)._tc is table.cell(1, 2)._tc
    assert table.cell(0, 0).text == "Merged"
    assert table.cell(1, 0).text == "A"
    assert table.cell(1, 1).text == "B"


def test_docx_export_writes_native_footnotes(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "First claim"},
                    {"type": "footnote", "attrs": {"id": "fn-a", "text": "First note."}},
                    {"type": "text", "text": " and second claim"},
                    {"type": "footnote", "attrs": {"id": "fn-b", "text": "Second note."}},
                    {"type": "text", "text": "."},
                ],
            }
        ],
    }
    data = render_docx(content, tmp_path)

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        assert "word/footnotes.xml" in names
        footnotes = archive.read("word/footnotes.xml").decode("utf-8")
        body = archive.read("word/document.xml").decode("utf-8")
        rels = archive.read("word/_rels/document.xml.rels").decode("utf-8")
        content_types = archive.read("[Content_Types].xml").decode("utf-8")
        styles = archive.read("word/styles.xml").decode("utf-8")

        # Every XML part in the package must still be parseable.
        for name in names:
            if name.endswith(".xml") or name.endswith(".rels"):
                etree.fromstring(archive.read(name))

    assert 'w:footnoteReference w:id="1"' in body
    assert 'w:footnoteReference w:id="2"' in body
    assert 'w:type="separator" w:id="-1"' in footnotes
    assert 'w:type="continuationSeparator" w:id="0"' in footnotes
    assert 'w:id="1"' in footnotes and "First note." in footnotes
    assert 'w:id="2"' in footnotes and "Second note." in footnotes
    assert "relationships/footnotes" in rels
    assert "wordprocessingml.footnotes+xml" in content_types
    assert "FootnoteReference" in styles
    assert "FootnoteText" in styles


def test_docx_footnote_text_is_escaped_and_multiline(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Claim"},
                    {
                        "type": "footnote",
                        "attrs": {"id": "fn-a", "text": "A < B & C\nsecond line"},
                    },
                ],
            }
        ],
    }
    data = render_docx(content, tmp_path)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        footnotes = archive.read("word/footnotes.xml").decode("utf-8")
        etree.fromstring(archive.read("word/footnotes.xml"))

    # Markup characters must be escaped, not injected into the package.
    assert "A &lt; B &amp; C" in footnotes
    assert "<w:br/>" in footnotes


def test_docx_without_footnotes_has_no_footnotes_part(tmp_path: Path) -> None:
    content = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Plain"}]}
        ],
    }
    data = render_docx(content, tmp_path)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert "word/footnotes.xml" not in archive.namelist()


def test_export_endpoint_returns_docx(client: TestClient, project: dict) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Body text."}],
            },
            {"type": "blockMath", "attrs": {"latex": "a = b"}},
        ],
    }
    saved = client.put(
        f"/api/projects/{project['id']}/document",
        json={"content": content, "plain_text": "Body text."},
    )
    assert saved.status_code == 200, saved.text

    response = client.get(
        f"/api/projects/{project['id']}/document/export",
        params={"format": "docx"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'filename="Quantum-Mechanics.docx"' in response.headers[
        "content-disposition"
    ]
    assert response.content[:2] == b"PK"

    document = Document(io.BytesIO(response.content))
    assert any("Body text." in text for text in _paragraph_texts(document))
    assert "oMath" in _body_xml(document)

    history = client.get(f"/api/projects/{project['id']}/history").json()
    exported = [
        event for event in history if event.get("event_type") == "document_exported"
    ]
    assert exported
    assert exported[0]["payload"]["format"] == "docx"
    assert exported[0]["payload"]["byte_size"] == len(response.content)
