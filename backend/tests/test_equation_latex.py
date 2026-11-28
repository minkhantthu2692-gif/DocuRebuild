from __future__ import annotations

from app.services.equation_latex import (
    equation_latex_from_words,
    normalize_math_text,
)


def _word(text: str, x: float, y: float, width: float, height: float, line: int = 0):
    return {
        "text": text,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "line": line,
        "confidence": 90.0,
    }


def test_normalize_maps_unicode_math_to_latex() -> None:
    assert normalize_math_text("3×4 ≤ 5 − 2") == r"3\times4 \leq 5 - 2"
    assert normalize_math_text("θ = π") == r"\theta = \pi"
    assert normalize_math_text("∫ f(x) dx") == r"\int f(x) dx"
    assert normalize_math_text("Δ = Σx²") == r"\Delta = \Sigma x^2"


def test_normalize_keeps_characters_the_engine_read() -> None:
    # A misread digit is preserved: nothing is guessed back to the original.
    assert normalize_math_text("I(20) = (1°)") == r"I(20) = (1^\circ)"
    assert normalize_math_text("E = mc²") == "E = mc^2"
    assert normalize_math_text("x_i = 2⁵") == "x_i = 2^5"


def test_normalize_expands_function_names_and_escapes() -> None:
    assert normalize_math_text("cos²(2θ)") == r"\cos^2(2\theta)"
    # A variable that merely starts with a function name stays untouched.
    assert normalize_math_text("cosine") == "cosine"
    # An existing command is not escaped a second time.
    assert normalize_math_text(r"\cos x") == r"\cos x"
    assert normalize_math_text("50% & 20#") == r"50\% \& 20\#"


def test_normalize_collapses_whitespace_and_line_breaks() -> None:
    assert normalize_math_text("a\n  b") == "a b"
    assert normalize_math_text("  ") == ""
    assert normalize_math_text("") == ""


def test_normalize_drops_the_space_a_line_break_leaves_inside_brackets() -> None:
    # Math mode ignores it, but the source the user edits should not carry it.
    assert normalize_math_text("(1°\n)K") == r"(1^\circ)K"
    assert normalize_math_text("[ 1 + 2 ]") == "[1 + 2]"
    # Spaces that separate terms rather than sit inside brackets are kept.
    assert normalize_math_text("a +\n b") == "a + b"


def test_words_lift_a_clearly_smaller_word_into_a_superscript() -> None:
    words = [
        _word("I", 0, 100, 24, 24),
        _word("0", 24, 96, 12, 12),
    ]
    assert equation_latex_from_words(words) == "I^{0}"


def test_words_lift_a_lower_small_word_into_a_subscript() -> None:
    words = [
        _word("x", 0, 100, 24, 24),
        _word("i", 24, 112, 12, 12),
    ]
    assert equation_latex_from_words(words) == "x_{i}"


def test_words_leave_ambiguous_boxes_on_the_baseline() -> None:
    # Two words of the same height are both normal, not scripts.
    words = [
        _word("a", 0, 100, 24, 24),
        _word("b", 30, 100, 24, 24),
    ]
    assert equation_latex_from_words(words) == "a b"


def test_words_group_by_line_and_are_joined_in_order() -> None:
    words = [
        _word("x", 0, 100, 20, 20, line=0),
        _word("=", 0, 130, 20, 20, line=1),
        _word("1", 0, 160, 20, 20, line=2),
    ]
    assert equation_latex_from_words(words) == "x = 1"


def test_missing_or_malformed_words_fall_back_to_normalised_text() -> None:
    assert equation_latex_from_words([], "E = mc²") == "E = mc^2"
    assert equation_latex_from_words([{"text": ""}], "E = mc²") == "E = mc^2"
    assert (
        equation_latex_from_words([{"text": "a", "x": "bad"}], "E = mc²")
        == "E = mc^2"
    )
    assert equation_latex_from_words([], "") == ""


def test_a_misread_character_is_never_invented() -> None:
    # The example's OCR read the degree sign for I^0; only the glyph that was
    # actually read is mapped, the surrounding characters stay as they are. The
    # space the OCR line break left before the bracket is dropped.
    assert normalize_math_text("(1°)K (1 + cos²(20) : ]") == (
        r"(1^\circ)K (1 + \cos^2(20) :]"
    )
