from __future__ import annotations

import io
import json
import sys
import unicodedata
from pathlib import Path
from typing import Sequence

import pytest

from app import ocr_benchmark
from app.core.errors import AppError
from app.ocr_benchmark import (
    BenchmarkCase,
    BenchmarkError,
    _edit_distance,
    character_error_rate,
    load_manifest,
    main,
    normalize_text,
    run_cases,
    score_text,
    word_error_rate,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _manifest(folder: Path, payload: object) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "manifest.json"
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )
    return path


def _naive_distance(left: Sequence[str], right: Sequence[str]) -> int:
    previous = list(range(len(right) + 1))
    for row, left_item in enumerate(left, start=1):
        current = [row]
        for column, right_item in enumerate(right, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (0 if left_item == right_item else 1),
                )
            )
        previous = current
    return previous[-1]


def test_normalize_text_uses_nfc_and_collapses_whitespace() -> None:
    assert normalize_text("Cafe\u0301") == "Caf\u00e9"
    assert normalize_text("  first\nsecond\t\tthird  ") == "first second third"
    # Case, punctuation and Burmese marks stay significant.
    assert normalize_text("Hello, World!") == "Hello, World!"
    assert normalize_text("\u1019\u103c\u1014\u103a\u1019\u102c") == (
        "\u1019\u103c\u1014\u103a\u1019\u102c"
    )


def test_character_error_rate_counts_substitutions() -> None:
    assert character_error_rate("abcd", "abcd") == 0.0
    assert character_error_rate("abcd", "abxd") == pytest.approx(0.25)
    assert character_error_rate("abcd", "abcd!") == pytest.approx(0.25)
    assert character_error_rate("abcd", "abd") == pytest.approx(0.25)


def test_whitespace_and_unicode_form_are_not_errors() -> None:
    assert character_error_rate("hello\nworld", "hello world") == 0.0
    assert character_error_rate("Cafe\u0301", "Caf\u00e9") == 0.0
    assert word_error_rate("one\ntwo", "one two") == 0.0


def test_empty_reference_cannot_look_perfect() -> None:
    assert character_error_rate("", "") == 0.0
    assert character_error_rate("", "anything") == 1.0
    assert word_error_rate("", "anything") == 1.0


def test_word_error_rate_counts_whole_words() -> None:
    assert word_error_rate("the quick brown fox", "the quick brown box") == (
        pytest.approx(0.25)
    )
    # A split word is one word error plus one insertion.
    assert word_error_rate("cannot", "can not") == pytest.approx(2.0)


def test_burmese_characters_are_scored_per_code_point() -> None:
    reference = "\u1019\u103c\u1014\u103a\u1019\u102c"
    assert character_error_rate(reference, reference) == 0.0
    assert character_error_rate(reference, reference[:-1]) == pytest.approx(
        1 / len(reference)
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("", ""),
        ("a", ""),
        ("", "abc"),
        ("abc", "abc"),
        ("prefix-middle-suffix", "prefix-muddle-suffix"),
        ("kitten", "sitting"),
        ("same start", "same start and more"),
        ("different", "entirely"),
        ("aaa", "aaaa"),
        ("abcabc", "abc"),
    ],
)
def test_edit_distance_matches_a_naive_implementation(left: str, right: str) -> None:
    assert _edit_distance(left, right) == _naive_distance(left, right)
    assert _edit_distance(right, left) == _naive_distance(right, left)


def test_edit_distance_matches_naive_on_random_sequences() -> None:
    """The bit-parallel implementation must not drift from the definition."""
    import random

    rng = random.Random(20261115)
    alphabet = "abcde \u1019\u103c"
    for _ in range(400):
        left = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 18)))
        right = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 18)))
        assert _edit_distance(left, right) == _naive_distance(left, right)
        # The same routine scores word lists, where each item is one unit.
        left_words = left.split()
        right_words = right.split()
        assert _edit_distance(left_words, right_words) == _naive_distance(
            left_words, right_words
        )


def test_score_text_reports_edits_and_reference_size() -> None:
    score = score_text("alpha beta gamma", "alpha beta ganna")
    assert score["reference_characters"] == len("alpha beta gamma")
    assert score["reference_words"] == 3
    # gamma -> ganna is two character substitutions but one word error.
    assert score["character_edits"] == 2
    assert score["word_edits"] == 1
    assert score["character_error_rate"] == pytest.approx(2 / 16)
    assert score["word_error_rate"] == pytest.approx(1 / 3)


def test_load_manifest_reads_image_and_stored_transcript_cases(tmp_path: Path) -> None:
    folder = tmp_path / "fixtures"
    _write(folder / "english" / "page-1.png", "not really an image")
    _write(folder / "english" / "page-1.txt", "Correct text")
    _write(folder / "burmese" / "page-1.txt", "Correct text")
    _write(folder / "burmese" / "page-1.ocr.txt", "Engine text")
    _manifest(
        folder,
        {
            "cases": [
                {
                    "name": "english-page-1",
                    "category": "english",
                    "languages": ["eng"],
                    "image": "english/page-1.png",
                    "reference": "english/page-1.txt",
                },
                {
                    "name": "burmese-page-1",
                    "hypothesis": "burmese/page-1.ocr.txt",
                    "reference": "burmese/page-1.txt",
                },
            ]
        },
    )

    cases = load_manifest(folder)

    assert [case.name for case in cases] == ["english-page-1", "burmese-page-1"]
    assert cases[0].category == "english"
    assert cases[0].languages == ("eng",)
    assert cases[0].image is not None
    assert cases[0].hypothesis is None
    assert cases[0].source == "ocr"
    # Defaults keep a plain case usable without extra configuration.
    assert cases[1].category == ocr_benchmark.DEFAULT_CATEGORY
    assert cases[1].languages == ocr_benchmark.DEFAULT_LANGUAGES
    assert cases[1].image is None
    assert cases[1].source == "stored transcript"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("{", "cannot be read"),
        ({"cases": []}, "non-empty cases list"),
        ({"cases": ["not an object"]}, "must be a JSON object"),
        (
            {"cases": [{"name": "a", "reference": "a.txt"}]},
            "exactly one of image or hypothesis",
        ),
        (
            {
                "cases": [
                    {
                        "name": "a",
                        "image": "a.png",
                        "hypothesis": "a.txt",
                        "reference": "a.txt",
                    }
                ]
            },
            "exactly one of image or hypothesis",
        ),
        (
            {"cases": [{"name": "a", "hypothesis": "a.txt"}]},
            "needs a reference path",
        ),
        (
            {"cases": [{"name": "a", "hypothesis": "a.txt", "reference": "../a.txt"}]},
            "must stay inside the fixtures folder",
        ),
        (
            {
                "cases": [
                    {"name": "a", "hypothesis": "missing.txt", "reference": "a.txt"}
                ]
            },
            "was not found",
        ),
        (
            {
                "cases": [
                    {"name": "a", "hypothesis": "a.txt", "reference": "a.txt"},
                    {"name": "a", "hypothesis": "b.txt", "reference": "b.txt"},
                ]
            },
            "used more than once",
        ),
        (
            {
                "cases": [
                    {
                        "name": "a",
                        "languages": [],
                        "hypothesis": "a.txt",
                        "reference": "a.txt",
                    }
                ]
            },
            "languages must be a non-empty list",
        ),
    ],
)
def test_load_manifest_rejects_unusable_fixtures(
    tmp_path: Path, payload: object, message: str
) -> None:
    folder = tmp_path / "fixtures"
    _write(folder / "a.txt", "text")
    _write(folder / "b.txt", "text")
    _manifest(folder, payload)

    with pytest.raises(BenchmarkError, match=message):
        load_manifest(folder)


def test_load_manifest_rejects_a_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkError, match="was not found"):
        load_manifest(tmp_path / "absent")


def _stored_cases(tmp_path: Path) -> list[BenchmarkCase]:
    folder = tmp_path / "fixtures"
    _write(folder / "one.txt", "alpha beta gamma")
    _write(folder / "one.ocr.txt", "alpha beta ganna")
    _write(folder / "two.txt", "delta epsilon")
    _write(folder / "two.ocr.txt", "delta epsilon")
    _write(folder / "three.txt", "zeta eta theta")
    _write(folder / "three.ocr.txt", "zeta eta")
    _manifest(
        folder,
        {
            "cases": [
                {
                    "name": "one",
                    "category": "english",
                    "hypothesis": "one.ocr.txt",
                    "reference": "one.txt",
                },
                {
                    "name": "two",
                    "category": "english",
                    "hypothesis": "two.ocr.txt",
                    "reference": "two.txt",
                },
                {
                    "name": "three",
                    "category": "mixed",
                    "hypothesis": "three.ocr.txt",
                    "reference": "three.txt",
                },
            ]
        },
    )
    return load_manifest(folder)


def test_run_cases_aggregates_by_reference_length(tmp_path: Path) -> None:
    report = run_cases(_stored_cases(tmp_path))

    assert report["errors"] == 0
    assert [case["name"] for case in report["cases"]] == ["one", "two", "three"]
    # 2 substitutions in "one" and 6 deleted characters in "three", over 43
    # reference characters: totals are weighted, not a mean of case ratios.
    assert report["overall"]["character_edits"] == 8
    assert report["overall"]["word_edits"] == 2
    assert report["overall"]["reference_characters"] == 43
    assert report["overall"]["reference_words"] == 8
    assert report["overall"]["character_error_rate"] == pytest.approx(8 / 43)
    assert [group["category"] for group in report["categories"]] == [
        "english",
        "mixed",
    ]
    assert report["categories"][0]["cases"] == 2
    assert report["categories"][0]["reference_characters"] == 29


def test_run_cases_uses_the_local_engine_and_keeps_its_details(tmp_path: Path) -> None:
    folder = tmp_path / "fixtures"
    _write(folder / "page.png", "image bytes")
    _write(folder / "page.txt", "hello world")
    _manifest(
        folder,
        {
            "cases": [
                {
                    "name": "page",
                    "category": "english",
                    "languages": ["eng", "mya"],
                    "image": "page.png",
                    "reference": "page.txt",
                }
            ]
        },
    )
    calls: list[tuple[str, list[str]]] = []

    def runner(path: Path, languages: list[str]) -> dict:
        calls.append((path.name, languages))
        return {
            "text": "hello world",
            "engine": "tesseract",
            "engine_version": "5.3.0",
            "confidence": 92.5,
        }

    report = run_cases(load_manifest(folder), ocr_runner=runner)

    assert calls == [("page.png", ["eng", "mya"])]
    case = report["cases"][0]
    assert case["source"] == "ocr"
    assert case["engine"] == "tesseract"
    assert case["engine_version"] == "5.3.0"
    assert case["confidence"] == 92.5
    assert case["character_error_rate"] == 0.0


def test_a_case_that_cannot_be_scored_does_not_hide_the_others(tmp_path: Path) -> None:
    cases = _stored_cases(tmp_path)

    def runner(path: Path, languages: list[str]) -> dict:
        raise AppError(409, "ocr_unavailable", "No local OCR engine is available.")

    report = run_cases(cases, ocr_runner=runner)
    # Stored transcripts never call the runner, so the run is still complete.
    assert report["errors"] == 0

    image_case = BenchmarkCase(
        name="image",
        category="english",
        languages=("eng",),
        reference=cases[0].reference,
        image=cases[0].reference,
    )
    report = run_cases([image_case, *cases], ocr_runner=runner)
    assert report["errors"] == 1
    assert report["cases"][0]["error_code"] == "ocr_unavailable"
    assert report["overall"]["cases"] == 3
    assert report["overall"]["reference_characters"] == 43


def test_main_prints_a_json_report(tmp_path: Path, capsys) -> None:
    _stored_cases(tmp_path)

    assert main([str(tmp_path / "fixtures"), "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["overall"]["cases"] == 3
    assert report["overall"]["character_error_rate"] == pytest.approx(8 / 43)


def test_main_can_select_one_case(tmp_path: Path, capsys) -> None:
    _stored_cases(tmp_path)

    assert main([str(tmp_path / "fixtures"), "--json", "--case", "three"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert [case["name"] for case in report["cases"]] == ["three"]


def test_main_prints_a_readable_report(tmp_path: Path, capsys) -> None:
    _stored_cases(tmp_path)

    assert main([str(tmp_path / "fixtures")]) == 0

    output = capsys.readouterr().out
    assert "Local OCR accuracy benchmark" in output
    assert "one" in output
    assert "By category (weighted by reference length)" in output
    assert "Overall: 3 case(s)" in output


def test_main_prints_burmese_case_names_on_a_legacy_console(
    tmp_path: Path, monkeypatch
) -> None:
    """A redirected Windows console must not crash on a Burmese case name."""
    folder = tmp_path / "fixtures"
    _write(folder / "page.txt", "\u1019\u103c\u1014\u103a\u1019\u102c")
    _write(folder / "page.ocr.txt", "\u1019\u103c\u1014\u103a\u1019\u102c")
    _manifest(
        folder,
        {
            "cases": [
                {
                    "name": "\u1019\u103c\u1014\u103a\u1019\u102c-\u1041",
                    "hypothesis": "page.ocr.txt",
                    "reference": "page.txt",
                }
            ]
        },
    )
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", write_through=True)
    monkeypatch.setattr(sys, "stdout", stream)

    assert main([str(folder)]) == 0

    stream.flush()
    assert "\u1019\u103c\u1014\u103a\u1019\u102c-\u1041" in buffer.getvalue().decode("utf-8")


def test_main_reports_invalid_arguments_and_manifests(
    tmp_path: Path, capsys
) -> None:
    _stored_cases(tmp_path)

    assert main([str(tmp_path / "fixtures"), "--case", "absent"]) == 2
    assert "unknown case" in capsys.readouterr().err

    assert main([str(tmp_path / "absent")]) == 2
    assert "was not found" in capsys.readouterr().err


def test_main_returns_one_when_a_case_could_not_be_scored(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    folder = tmp_path / "fixtures"
    _write(folder / "page.png", "image bytes")
    _write(folder / "page.txt", "hello")
    _manifest(
        folder,
        {
            "cases": [
                {
                    "name": "page",
                    "image": "page.png",
                    "reference": "page.txt",
                }
            ]
        },
    )

    def unavailable(path: Path, languages: list[str]) -> dict:
        raise AppError(409, "ocr_unavailable", "No local OCR engine is available.")

    monkeypatch.setattr(ocr_benchmark.ocr_service, "extract_image_text", unavailable)

    assert main([str(folder)]) == 1
    output = capsys.readouterr().out
    assert "No local OCR engine is available." in output
    assert "could not be scored" in output

def test_main_passes_segmentation_mode_to_the_engine(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    folder = tmp_path / "fixtures"
    _write(folder / "page.png", "image bytes")
    _write(folder / "page.txt", "hello world")
    _manifest(
        folder,
        {
            "cases": [
                {
                    "name": "page",
                    "image": "page.png",
                    "reference": "page.txt",
                }
            ]
        },
    )

    calls: list[int | None] = []

    def extract(
        path: Path,
        languages: list[str],
        *,
        page_segmentation_mode: int | None = None,
    ) -> dict:
        calls.append(page_segmentation_mode)
        return {"text": "hello world", "engine": "tesseract", "confidence": 90.0}

    monkeypatch.setattr(ocr_benchmark.ocr_service, "extract_image_text", extract)

    assert main([str(folder), "--json", "--segmentation-mode", "11"]) == 0
    capsys.readouterr()
    assert calls == [11]


def test_main_rejects_an_unknown_segmentation_mode(tmp_path: Path) -> None:
    _stored_cases(tmp_path)

    with pytest.raises(SystemExit) as error:
        main([str(tmp_path / "fixtures"), "--segmentation-mode", "12"])

    assert error.value.code == 2


def test_the_committed_real_scan_corpus_is_usable() -> None:
    """The real-scan fixtures must stay loadable without running OCR.

    Scoring needs Tesseract, so this only checks the shape of the corpus that
    the documented results were measured from: a valid manifest, a reference for
    every case, and references that are non-empty and already in NFC. A
    decomposed Burmese reference would silently change what the published error
    rate means.
    """
    folder = Path(__file__).parent / "fixtures" / "ocr-real"

    cases = load_manifest(folder)

    assert [case.name for case in cases] == [
        "english-prose",
        "english-table",
        "burmese-mixed",
    ]
    assert [case.category for case in cases] == ["english", "table", "mixed"]
    assert [case.languages for case in cases] == [
        ("eng",),
        ("eng",),
        ("eng", "mya"),
    ]
    for case in cases:
        assert case.image is not None
        raw = case.reference.read_text(encoding="utf-8")
        assert unicodedata.normalize("NFC", raw) == raw
        assert normalize_text(raw)
