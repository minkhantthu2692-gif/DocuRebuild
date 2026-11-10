from __future__ import annotations

from app.services.layout import classify_text_block


def test_page_number_in_page_margin() -> None:
    assert (
        classify_text_block("42", 10.0, 10.0, 1, y=950.0, height=20.0, page_height=1000.0)
        == "page_number"
    )
    assert (
        classify_text_block("iii", 10.0, 10.0, 1, y=10.0, height=20.0, page_height=1000.0)
        == "page_number"
    )


def test_number_in_body_is_not_a_page_number() -> None:
    assert (
        classify_text_block("42", 10.0, 10.0, 1, y=500.0, height=20.0, page_height=1000.0)
        == "paragraph"
    )


def test_header_and_footer_need_page_margins() -> None:
    assert (
        classify_text_block(
            "A short running head",
            10.0,
            10.0,
            4,
            y=20.0,
            height=20.0,
            page_height=1000.0,
        )
        == "header"
    )
    assert (
        classify_text_block(
            "A short footer",
            10.0,
            10.0,
            3,
            y=955.0,
            height=20.0,
            page_height=1000.0,
        )
        == "footer"
    )
    assert (
        classify_text_block("A short sentence", 10.0, 10.0, 3, y=500.0, height=20.0)
        == "paragraph"
    )


def test_caption_candidates_require_a_label_and_boundary() -> None:
    assert (
        classify_text_block(
            "Figure 1.2: A labelled diagram", 10.0, 10.0, 5, y=300.0, height=20.0
        )
        == "caption"
    )
    assert (
        classify_text_block(
            "Table 1 shows the measured values.", 10.0, 10.0, 6, y=300.0, height=20.0
        )
        == "paragraph"
    )


def test_equation_candidates_keep_plain_sentences_as_paragraphs() -> None:
    assert classify_text_block("E = mc^2", 10.0, 10.0, 3) == "equation"
    assert (
        classify_text_block(
            "The result = 5 and it is correct.", 10.0, 10.0, 7
        )
        == "paragraph"
    )
    assert classify_text_block("2024-2025", 10.0, 10.0, 1) == "paragraph"


def test_table_candidates_need_aligned_column_gaps() -> None:
    spans = [
        [(0.0, 40.0), (200.0, 240.0), (400.0, 440.0)],
        [(0.0, 50.0), (205.0, 250.0), (405.0, 445.0)],
    ]
    assert (
        classify_text_block(
            "Name  Value  Unit\nMass  2  kg",
            20.0,
            20.0,
            6,
            line_spans=spans,
        )
        == "table"
    )

    plain_spans = [
        [(0.0, 30.0), (36.0, 60.0), (66.0, 90.0)],
        [(0.0, 32.0), (38.0, 62.0), (68.0, 92.0)],
    ]
    assert (
        classify_text_block(
            "This is a normal paragraph\nwith ordinary word spacing.",
            20.0,
            20.0,
            8,
            line_spans=plain_spans,
        )
        == "paragraph"
    )


def test_existing_heading_and_list_heuristics_are_preserved() -> None:
    assert classify_text_block("Chapter One", 20.0, 10.0, 2) == "heading"
    assert classify_text_block("- First item", 10.0, 10.0, 2) == "list_item"
