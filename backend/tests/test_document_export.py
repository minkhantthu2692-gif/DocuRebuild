from __future__ import annotations

from fastapi.testclient import TestClient
from urllib.parse import quote

from app.services.document_export import render_markdown, render_text, safe_filename


def _doc() -> dict:
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
                    {"type": "hardBreak"},
                    {"type": "text", "text": "Second line."},
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
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Fourth"}],
                            }
                        ],
                    },
                ],
            },
            {
                "type": "blockquote",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Quoted"}],
                    }
                ],
            },
            {
                "type": "codeBlock",
                "attrs": {"language": "python"},
                "content": [{"type": "text", "text": 'print("x")'}],
            },
            {"type": "horizontalRule"},
            {
                "type": "figure",
                "attrs": {
                    "src": "/api/projects/abc/assets/local-only.png",
                    "alt": "",
                    "caption": "Figure 1: Wavefunction",
                    "note": "Source: page 2",
                    "width": 640,
                    "height": 480,
                },
            },
        ],
    }


def test_markdown_export_renders_every_block() -> None:
    markdown = render_markdown(_doc())
    assert markdown.startswith("# Quantum Mechanics\n")
    assert "The **Schrödinger** equation.  \nSecond line." in markdown
    assert "- First\n- Second" in markdown
    assert "3. Third\n4. Fourth" in markdown
    assert "> Quoted" in markdown
    assert '```python\nprint("x")\n```' in markdown
    assert "\n---\n" in markdown
    assert "\\[Figure: Figure 1: Wavefunction\\]" in markdown
    assert "> Source: page 2" in markdown
    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")


def test_markdown_export_escapes_extracted_text() -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "# not a heading\n- not a list\n*star* <script> [link]",
                    }
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "1. not a list"},
                ],
            },
        ],
    }
    markdown = render_markdown(content)
    assert "\\# not a heading" in markdown
    assert "\\- not a list" in markdown
    assert "\\*star\\*" in markdown
    assert "\\<script\\>" in markdown
    assert "\\[link\\]" in markdown
    assert "1\\. not a list" in markdown
    # Escaped text must never become real Markdown structure.
    assert not markdown.startswith("# ")


def test_markdown_export_keeps_code_spans_literal() -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "**not bold**",
                        "marks": [{"type": "code"}],
                    }
                ],
            }
        ],
    }
    assert render_markdown(content) == "`**not bold**`\n"


def test_markdown_export_drops_unsafe_link_targets() -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "click",
                        "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}],
                    },
                    {"type": "text", "text": " "},
                    {
                        "type": "text",
                        "text": "safe",
                        "marks": [{"type": "link", "attrs": {"href": "https://example.com/a"}}],
                    },
                ],
            }
        ],
    }
    markdown = render_markdown(content)
    assert "javascript" not in markdown
    assert "click" in markdown
    assert "[safe](https://example.com/a)" in markdown


def test_text_export_is_plain_and_omits_asset_paths() -> None:
    text = render_text(_doc())
    assert "# Quantum Mechanics" not in text
    assert text.startswith("Quantum Mechanics\n")
    assert "- First\n- Second" in text
    assert "3. Third\n4. Fourth" in text
    assert "[Figure: Figure 1: Wavefunction]\nSource: page 2" in text
    assert "local-only.png" not in text
    assert "/api/" not in text


def test_markdown_export_omits_asset_paths() -> None:
    assert "/api/" not in render_markdown(_doc())


def _math_doc(*nodes: dict) -> dict:
    return {"type": "doc", "content": list(nodes)}


def test_markdown_export_writes_equations_as_math() -> None:
    content = _math_doc(
        {
            "type": "blockMath",
            "attrs": {"latex": r"\frac{a}{b} = \sum_{i=1}^{n} x_i"},
        },
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Inline "},
                {"type": "inlineMath", "attrs": {"latex": r"E = mc^2"}},
                {"type": "text", "text": " stays readable."},
            ],
        },
    )
    markdown = render_markdown(content)
    # LaTeX backslashes must survive; math is never escaped as prose.
    assert "$$\n\\frac{a}{b} = \\sum_{i=1}^{n} x_i\n$$" in markdown
    assert "Inline $E = mc^2$ stays readable." in markdown
    assert markdown.endswith("\n")


def test_text_export_keeps_equation_source() -> None:
    content = _math_doc(
        {"type": "blockMath", "attrs": {"latex": r"\int_0^1 x^2\,dx"}},
        {
            "type": "paragraph",
            "content": [{"type": "inlineMath", "attrs": {"latex": "a^2 + b^2"}}],
        },
    )
    text = render_text(content)
    assert "\\int_0^1 x^2\\,dx" in text
    assert "a^2 + b^2" in text
    assert "$$" not in text


def test_export_skips_equations_without_latex() -> None:
    content = _math_doc({"type": "blockMath", "attrs": {"latex": "   "}})
    assert render_markdown(content) == ""
    assert render_text(content) == ""


def test_numbered_equations_export_in_document_order() -> None:
    content = _math_doc(
        _paragraph("First,"),
        {"type": "blockMath", "attrs": {"latex": "a = b", "numbered": True}},
        _paragraph("then an unnumbered one,"),
        {"type": "blockMath", "attrs": {"latex": "c = d"}},
        {"type": "blockMath", "attrs": {"latex": "e = f", "numbered": True}},
    )
    markdown = render_markdown(content)
    assert "$$\na = b\n$$ (1)" in markdown
    assert "$$\nc = d\n$$" in markdown
    assert "$$\ne = f\n$$ (2)" in markdown
    # The numbering must never be part of the LaTeX source itself.
    assert "a = b (1)" not in markdown
    assert "\x00" not in markdown


def test_text_export_numbers_display_equations() -> None:
    content = _math_doc(
        {"type": "blockMath", "attrs": {"latex": "a = b", "numbered": True}},
        {"type": "blockMath", "attrs": {"latex": "c = d"}},
        {"type": "blockMath", "attrs": {"latex": "e = f", "numbered": True}},
    )
    text = render_text(content)
    assert "a = b (1)" in text
    assert "c = d" in text
    assert "e = f (2)" in text
    assert "\x00" not in text


def test_unnumbered_equations_stay_unchanged() -> None:
    content = _math_doc(
        {"type": "blockMath", "attrs": {"latex": "a = b", "numbered": False}},
        {
            "type": "paragraph",
            "content": [{"type": "inlineMath", "attrs": {"latex": "x^2"}}],
        },
    )
    markdown = render_markdown(content)
    assert markdown == "$$\na = b\n$$\n\n$x^2$\n"
    assert "(1)" not in markdown
    assert render_text(content) == "a = b\n\nx^2\n"


def _paragraph(text: str) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}] if text else [],
    }


def _cell(text: str, kind: str = "tableCell", **attrs: object) -> dict:
    return {
        "type": kind,
        "attrs": {"colspan": 1, "rowspan": 1, "colwidth": None, **attrs},
        "content": [_paragraph(text)],
    }


def _table_doc(*rows: list[dict]) -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": [{"type": "tableRow", "content": row} for row in rows],
            }
        ],
    }


def test_markdown_export_renders_tables_and_escapes_pipes() -> None:
    content = _table_doc(
        [_cell("Name", "tableHeader"), _cell("Value | unit", "tableHeader")],
        [_cell("Mass"), _cell("1.5 kg")],
    )
    markdown = render_markdown(content)
    assert "| Name | Value \\| unit |" in markdown
    assert "| --- | --- |" in markdown
    assert "| Mass | 1.5 kg |" in markdown


def test_markdown_export_keeps_multiple_paragraphs_inside_a_cell() -> None:
    content = _table_doc(
        [_cell("Term", "tableHeader")],
        [
            {
                "type": "tableCell",
                "attrs": {"colspan": 1, "rowspan": 1},
                "content": [_paragraph("First line"), _paragraph("Second line")],
            }
        ],
    )
    markdown = render_markdown(content)
    assert "First line<br>Second line" in markdown


def test_markdown_export_adds_a_structural_header_when_missing() -> None:
    content = _table_doc([_cell("x"), _cell("y")])
    markdown = render_markdown(content)
    assert markdown.startswith("|  |  |\n| --- | --- |\n")
    assert "| x | y |" in markdown


def test_markdown_export_uses_html_for_merged_cells() -> None:
    content = _table_doc(
        [
            _cell("A", "tableHeader", colspan=2),
            _cell("B", "tableHeader"),
        ],
        [_cell("C"), _cell("D"), _cell("E")],
    )
    markdown = render_markdown(content)
    # GFM cannot express spans; the exact structure is kept as HTML instead.
    assert "<th colspan=\"2\">A</th>" in markdown
    assert "<td>C</td>" in markdown
    assert markdown.count("A") == 1
    assert "| --- |" not in markdown


def test_text_export_keeps_every_table_cell() -> None:
    content = _table_doc(
        [_cell("Name", "tableHeader"), _cell("Value | unit", "tableHeader")],
        [_cell("Mass"), _cell("1.5 kg")],
        [_cell("Charge"), _cell("−1 e")],
    )
    text = render_text(content)
    assert "Name | Value | unit" in text
    assert "--- | ---" in text
    assert "Mass | 1.5 kg" in text
    assert "Charge | −1 e" in text


def test_text_export_keeps_merged_cell_content() -> None:
    content = _table_doc(
        [_cell("A", "tableHeader", colspan=2), _cell("B", "tableHeader")],
        [_cell("C"), _cell("D"), _cell("E")],
    )
    text = render_text(content)
    assert "A" in text and "B" in text
    assert "C | D | E" in text


def test_safe_filename_strips_path_characters() -> None:
    assert safe_filename('../../My Book: "draft"', "markdown") == "My-Book-draft.md"
    assert safe_filename("   ", "txt") == "document.txt"
    assert safe_filename("မြန်မာ", "txt") == "document.txt"


def test_export_endpoint_returns_markdown_attachment(
    client: TestClient, project: dict
) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Chapter"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Body text."}],
            },
        ],
    }
    saved = client.put(
        f"/api/projects/{project['id']}/document",
        json={"content": content, "plain_text": "Chapter\n\nBody text."},
    )
    assert saved.status_code == 200, saved.text

    response = client.get(f"/api/projects/{project['id']}/document/export")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="Quantum-Mechanics.md"')
    assert "filename*=UTF-8''Quantum%20Mechanics.md" in disposition
    assert response.text == "## Chapter\n\nBody text.\n"


def test_export_endpoint_returns_txt(client: TestClient, project: dict) -> None:
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Only text."}],
            }
        ],
    }
    client.put(
        f"/api/projects/{project['id']}/document",
        json={"content": content, "plain_text": "Only text."},
    )

    response = client.get(
        f"/api/projects/{project['id']}/document/export",
        params={"format": "txt"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert 'filename="Quantum-Mechanics.txt"' in response.headers["content-disposition"]
    assert response.text == "Only text.\n"


def test_export_endpoint_keeps_unicode_project_name(client: TestClient) -> None:
    created = client.post(
        "/api/projects",
        json={"name": "မြန်မာ စာအုပ်", "description": ""},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    response = client.get(f"/api/projects/{project_id}/document/export")
    assert response.status_code == 200, response.text
    disposition = response.headers["content-disposition"]
    assert quote("မြန်မာ စာအုပ်.md", safe="") in disposition
    assert 'filename="document.md"' in disposition


def test_export_endpoint_rejects_unknown_format(
    client: TestClient, project: dict
) -> None:
    response = client.get(
        f"/api/projects/{project['id']}/document/export",
        params={"format": "pdf"},
    )
    assert response.status_code == 422


def test_export_reports_missing_project(client: TestClient) -> None:
    response = client.get(
        "/api/projects/00000000-0000-0000-0000-000000000000/document/export"
    )
    assert response.status_code == 404


def test_meta_advertises_export(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert meta["capabilities"]["export"] is True
