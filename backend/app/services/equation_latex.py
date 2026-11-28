"""Turn OCR equation text into a faithful LaTeX starting point.

Tesseract returns plain text and word boxes, not LaTeX. This module maps the
Unicode math glyphs it does emit onto their LaTeX equivalents and reconstructs
the superscripts and subscripts its word boxes expose. It never guesses a
character the engine did not read: a misread digit stays the misread digit, so
the result is a reviewable starting point, not a silent correction.

Nothing here writes to the document. The equation dialog still renders the
preview locally and refuses to insert source the user has not seen.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any

Word = dict[str, Any]

# Every entry preserves the glyph's meaning; nothing adds a symbol the engine
# did not read. Keys are single characters because the map is applied per glyph.
_SYMBOLS: dict[str, str] = {
    "−": "-",
    "–": "-",
    "—": "-",
    "‒": "-",
    "×": r"\times",
    "·": r"\cdot",
    "÷": r"\div",
    "±": r"\pm",
    "∓": r"\mp",
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "≡": r"\equiv",
    "≅": r"\cong",
    "∝": r"\propto",
    "∞": r"\infty",
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "∮": r"\oint",
    "√": r"\sqrt",
    "∂": r"\partial",
    "∇": r"\nabla",
    "∈": r"\in",
    "∉": r"\notin",
    "⊂": r"\subset",
    "⊃": r"\supset",
    "⊆": r"\subseteq",
    "⊇": r"\supseteq",
    "∪": r"\cup",
    "∩": r"\cap",
    "→": r"\to",
    "←": r"\leftarrow",
    "↔": r"\leftrightarrow",
    "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow",
    "⇔": r"\Leftrightarrow",
    "°": r"^\circ",
    "′": "'",
    "″": "''",
    "…": r"\ldots",
    "⋯": r"\cdots",
    "∗": "*",
    "∙": r"\cdot",
    # Greek lower case.
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\phi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    # Greek upper case (the letters that differ from Latin).
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Υ": r"\Upsilon",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
}

_SUPERSCRIPTS: dict[str, str] = {
    "⁰": "^0",
    "¹": "^1",
    "²": "^2",
    "³": "^3",
    "⁴": "^4",
    "⁵": "^5",
    "⁶": "^6",
    "⁷": "^7",
    "⁸": "^8",
    "⁹": "^9",
    "⁺": "^+",
    "⁻": "^-",
    "⁼": "^=",
    "⁽": "^(",
    "⁾": "^)",
    "ⁿ": "^n",
    "ⁱ": "^i",
}

_SUBSCRIPTS: dict[str, str] = {
    "₀": "_0",
    "₁": "_1",
    "₂": "_2",
    "₃": "_3",
    "₄": "_4",
    "₅": "_5",
    "₆": "_6",
    "₇": "_7",
    "₈": "_8",
    "₉": "_9",
    "₊": "_+",
    "₋": "_-",
    "₌": "_=",
    "₍": "_(",
    "₎": "_)",
}

_ESCAPES = {"%": r"\%", "#": r"\#", "&": r"\&", "$": r"\$"}

# Function names become their command only when they stand as a word, so a
# variable such as ``cosine`` keeps its letters. A preceding backslash is not
# re-escaped if the text already carries a command.
_FUNCTIONS = (
    "arcsin",
    "arccos",
    "arctan",
    "sinh",
    "cosh",
    "tanh",
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "log",
    "ln",
    "exp",
    "lim",
    "max",
    "min",
    "det",
    "gcd",
)
_FUNCTION_RE = re.compile(r"(?<!\\)\b(" + "|".join(_FUNCTIONS) + r")\b")


def _map_glyphs(text: str) -> str:
    out: list[str] = []
    for index, char in enumerate(text):
        if char in _SUPERSCRIPTS:
            out.append(_SUPERSCRIPTS[char])
        elif char in _SUBSCRIPTS:
            out.append(_SUBSCRIPTS[char])
        elif char in _SYMBOLS:
            replacement = _SYMBOLS[char]
            out.append(replacement)
            # A multi-letter command followed by a letter would swallow it into
            # the command name (``\Sigmax``), so the two are separated here,
            # while the command boundary is still known. Control symbols such as
            # ``\%`` end on their own and need no gap.
            if (
                replacement.startswith("\\")
                and len(replacement) > 1
                and replacement[1].isalpha()
                and index + 1 < len(text)
                and text[index + 1].isascii()
                and text[index + 1].isalpha()
            ):
                out.append(" ")
        elif char in _ESCAPES:
            out.append(_ESCAPES[char])
        else:
            out.append(char)
    return "".join(out)


def normalize_math_text(text: str) -> str:
    """Map OCR text to LaTeX without inventing content.

    Whitespace and line breaks collapse to single spaces, Unicode math glyphs
    become their LaTeX commands and known function names get their command. A
    character the engine read stays exactly as read.
    """
    if not text:
        return ""
    mapped = _map_glyphs(text)
    mapped = _FUNCTION_RE.sub(lambda match: "\\" + match.group(1), mapped)
    # An OCR line break inside brackets leaves a stray space: ``(1^\\circ\\n)``
    # becomes ``(1^\\circ )``. Spaces inside brackets are ignored in math mode,
    # so dropping them only tidies the source the user edits.
    for opening, closing in (("(", ")"), ("[", "]"), ("{", "}")):
        mapped = re.sub(rf"\{opening}\s+", opening, mapped)
        mapped = re.sub(rf"\s+\{closing}", closing, mapped)
    return re.sub(r"\s+", " ", mapped).strip()


def _usable_words(words: list[Any]) -> list[Word]:
    """Keep word boxes with text and positive geometry; drop anything else."""
    usable: list[Word] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        text = word.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            x = float(word["x"])
            y = float(word["y"])
            width = float(word["width"])
            height = float(word["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        try:
            line = int(word.get("line", 0) or 0)
        except (TypeError, ValueError):
            line = 0
        usable.append(
            {
                "text": text.strip(),
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "line": line,
            }
        )
    return usable


def _group_lines(words: list[Word]) -> list[list[Word]]:
    grouped: dict[int, list[Word]] = {}
    for word in words:
        grouped.setdefault(word["line"], []).append(word)
    return [
        sorted(grouped[line], key=lambda item: item["x"])
        for line in sorted(grouped)
    ]


def _line_latex(line: list[Word]) -> str:
    """Render one visual line, lifting clearly smaller words into scripts.

    A word becomes a superscript or subscript only when it is markedly smaller
    than the line's typical word and its centre sits clearly above or below the
    line centre. Ambiguous boxes stay on the baseline.
    """
    heights = [word["height"] for word in line]
    reference = median(heights) if heights else 0.0
    top = min(word["y"] for word in line)
    bottom = max(word["y"] + word["height"] for word in line)
    centre = (top + bottom) / 2

    result = ""
    for word in line:
        text = normalize_math_text(word["text"])
        if not text:
            continue
        height = word["height"]
        word_centre = word["y"] + height / 2
        smaller = reference > 0 and height <= reference * 0.72
        if smaller and word_centre < centre - reference * 0.15:
            text = "^{" + text + "}"
        elif smaller and word_centre > centre + reference * 0.15:
            text = "_{" + text + "}"
        if not result:
            result = text
        elif text.startswith("^") or text.startswith("_"):
            result += text
        else:
            result += " " + text
    return result.strip()


def equation_latex_from_words(words: list[Any], fallback: str = "") -> str:
    """Build a LaTeX starting point from stored OCR word boxes.

    Superscripts and subscripts are recognised from the boxes; when the boxes
    are missing or unusable the plain OCR text is normalised instead. The result
    is never written to the document without the user reviewing the preview.
    """
    usable = _usable_words(words)
    if not usable:
        return normalize_math_text(fallback)
    lines = [_line_latex(line) for line in _group_lines(usable)]
    joined = " ".join(line for line in lines if line).strip()
    return joined or normalize_math_text(fallback)
