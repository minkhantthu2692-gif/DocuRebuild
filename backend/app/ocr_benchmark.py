"""Measure local OCR accuracy against reference transcripts.

OCR quality is easy to overstate. This module scores the local engine against
text a person has checked, using Character Error Rate (CER) and Word Error Rate
(WER), so an accuracy claim can be backed by a number. It runs on the machine
that owns the images: nothing is uploaded, and no AI provider is involved.

A fixtures folder contains ``manifest.json`` and the reference transcripts:

    {
      "cases": [
        {
          "name": "english-page-1",
          "category": "english",
          "languages": ["eng"],
          "image": "english/page-1.png",
          "reference": "english/page-1.txt"
        },
        {
          "name": "burmese-page-1",
          "category": "burmese",
          "hypothesis": "burmese/page-1.ocr.txt",
          "reference": "burmese/page-1.txt"
        }
      ]
    }

A case with ``image`` runs the same Tesseract adapter the application uses. A
case with ``hypothesis`` scores an already stored transcript, so an engine result
can be compared on a machine without Tesseract. Exactly one of the two is
required. ``reference`` is the correct text, and ``category`` groups results.

Text is normalised to NFC with collapsed whitespace before scoring. Case,
punctuation and Burmese combining marks are kept as they are, and no
Zawgyi/Unicode conversion is performed: the benchmark measures what the engine
produced, not what a conversion could have produced.

Run it with ``python -m app.ocr_benchmark <fixtures-folder>``. Add
``--segmentation-mode`` to score a specific Tesseract page layout mode (3
automatic, 4 single column, 6 single block, 11 sparse text) instead of the
configured default, which is how the Burmese page setting is evaluated. Exit
codes are 0 when every case was scored, 1 when at least one case could not be
scored and 2 for an invalid manifest or argument.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from app.core.errors import AppError
from app.core.storage import resolve_within
from app.services import ocr as ocr_service

MANIFEST_NAME = "manifest.json"
DEFAULT_CATEGORY = "uncategorised"
DEFAULT_LANGUAGES = ("eng",)
MAX_NAME_LENGTH = 120


class BenchmarkError(ValueError):
    """A fixtures folder or argument that cannot be used for scoring."""


@dataclass(frozen=True)
class BenchmarkCase:
    """One page whose OCR output is compared with a checked reference."""

    name: str
    category: str
    languages: tuple[str, ...]
    reference: Path
    image: Path | None = None
    hypothesis: Path | None = None

    @property
    def source(self) -> str:
        return "ocr" if self.image is not None else "stored transcript"


def normalize_text(text: str) -> str:
    """Return text in the comparison form used by every metric.

    NFC keeps precomposed and decomposed Latin forms comparable. Collapsing
    whitespace removes line wrapping differences, which are a layout artifact
    rather than a recognition error. Nothing else is changed: case, punctuation
    and combining marks stay significant.
    """
    return " ".join(unicodedata.normalize("NFC", text).split())


def _edit_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    """Levenshtein distance over any comparable sequence.

    Myers' bit-parallel algorithm stores one pattern position per bit, so a
    page-sized comparison runs in milliseconds instead of seconds. Big-integer
    operations are used as the bit vectors, which Python implements in C.
    """
    if reference == hypothesis:
        return 0

    # Distance is symmetric; making the shorter sequence the bit pattern keeps
    # every integer operation small.
    if len(reference) > len(hypothesis):
        reference, hypothesis = hypothesis, reference
    pattern_length = len(reference)
    if pattern_length == 0:
        return len(hypothesis)

    positions: dict[str, int] = {}
    for index, item in enumerate(reference):
        positions[item] = positions.get(item, 0) | (1 << index)

    mask = (1 << pattern_length) - 1
    high_bit = 1 << (pattern_length - 1)
    # pv/mv are the vertical deltas; ph/mh the horizontal ones.
    pv = mask
    mv = 0
    distance = pattern_length
    for item in hypothesis:
        eq = positions.get(item, 0)
        xv = eq | mv
        xh = (((eq & pv) + pv) ^ pv) | eq
        ph = mv | ~(xh | pv)
        mh = pv & xh
        if ph & high_bit:
            distance += 1
        elif mh & high_bit:
            distance -= 1
        ph = ((ph << 1) | 1) & mask
        mh = (mh << 1) & mask
        pv = (mh | ~(xv | ph)) & mask
        mv = ph & xv
    return distance


def _rate(edits: int, reference_units: int) -> float:
    """Turn an edit count into a ratio.

    An empty reference cannot produce a ratio. Empty output scores 0.0, while any
    output scores 1.0 rather than being silently dropped, so an empty reference
    can never make the run look better than it is.
    """
    if reference_units == 0:
        return 0.0 if edits == 0 else 1.0
    return edits / reference_units


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Share of reference characters that had to be inserted, deleted or changed."""
    expected = normalize_text(reference)
    return _rate(_edit_distance(expected, normalize_text(hypothesis)), len(expected))


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Share of reference words that had to be inserted, deleted or changed."""
    expected = normalize_text(reference)
    produced = normalize_text(hypothesis)
    expected_words = expected.split(" ") if expected else []
    produced_words = produced.split(" ") if produced else []
    return _rate(
        _edit_distance(expected_words, produced_words), len(expected_words)
    )


def score_text(reference: str, hypothesis: str) -> dict[str, Any]:
    """Score one transcript against the correct text."""
    expected = normalize_text(reference)
    produced = normalize_text(hypothesis)
    expected_words = expected.split(" ") if expected else []
    produced_words = produced.split(" ") if produced else []

    character_edits = _edit_distance(expected, produced)
    word_edits = _edit_distance(expected_words, produced_words)
    return {
        "character_edits": character_edits,
        "word_edits": word_edits,
        "reference_characters": len(expected),
        "reference_words": len(expected_words),
        "character_error_rate": _rate(character_edits, len(expected)),
        "word_error_rate": _rate(word_edits, len(expected_words)),
    }


def _aggregate(scores: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Combine cases by total edits over total reference units.

    Weighting by reference length stops one short line from counting as much as
    a full page. A plain mean of per-case rates would do exactly that.
    """
    character_edits = sum(score["character_edits"] for score in scores)
    word_edits = sum(score["word_edits"] for score in scores)
    characters = sum(score["reference_characters"] for score in scores)
    words = sum(score["reference_words"] for score in scores)
    return {
        "cases": len(scores),
        "character_edits": character_edits,
        "word_edits": word_edits,
        "reference_characters": characters,
        "reference_words": words,
        "character_error_rate": _rate(character_edits, characters),
        "word_error_rate": _rate(word_edits, words),
    }


def _clean_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkError(f"{label} must be a non-empty string.")
    name = value.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise BenchmarkError(f"{label} must be at most {MAX_NAME_LENGTH} characters.")
    return name


def _fixture_file(root: Path, value: Any, field: str, case_name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkError(f"Case {case_name!r} needs a {field} path.")
    try:
        path = resolve_within(root, value)
    except ValueError as exc:
        raise BenchmarkError(
            f"Case {case_name!r}: {field} must stay inside the fixtures folder."
        ) from exc
    if not path.is_file():
        raise BenchmarkError(
            f"Case {case_name!r}: {field} file was not found: {value}"
        )
    return path


def _languages(value: Any, case_name: str) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_LANGUAGES
    if not isinstance(value, list) or not value:
        raise BenchmarkError(
            f"Case {case_name!r}: languages must be a non-empty list."
        )
    languages: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise BenchmarkError(
                f"Case {case_name!r}: every language must be a non-empty string."
            )
        languages.append(item.strip())
    return tuple(languages)


def load_manifest(folder: Path | str) -> list[BenchmarkCase]:
    """Read and validate a fixtures folder without running OCR."""
    root = Path(folder)
    if not root.is_dir():
        raise BenchmarkError(f"The fixtures folder was not found: {root}")
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise BenchmarkError(f"The fixtures folder has no {MANIFEST_NAME}: {root}")
    try:
        # A BOM is an encoding marker, not content; utf-8-sig accepts both forms.
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"{MANIFEST_NAME} cannot be read: {exc}") from exc
    if not isinstance(payload, dict):
        raise BenchmarkError(f"{MANIFEST_NAME} must contain a JSON object.")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkError(f"{MANIFEST_NAME} needs a non-empty cases list.")

    cases: list[BenchmarkCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases, start=1):
        if not isinstance(raw, dict):
            raise BenchmarkError(f"Case {index} must be a JSON object.")
        name = _clean_name(raw.get("name"), f"Case {index} name")
        if name in seen:
            raise BenchmarkError(f"Case name {name!r} is used more than once.")
        seen.add(name)

        category = DEFAULT_CATEGORY
        if raw.get("category") is not None:
            category = _clean_name(raw.get("category"), f"Case {name!r} category")

        image_value = raw.get("image")
        hypothesis_value = raw.get("hypothesis")
        if (image_value is None) == (hypothesis_value is None):
            raise BenchmarkError(
                f"Case {name!r} needs exactly one of image or hypothesis."
            )

        cases.append(
            BenchmarkCase(
                name=name,
                category=category,
                languages=_languages(raw.get("languages"), name),
                reference=_fixture_file(root, raw.get("reference"), "reference", name),
                image=(
                    _fixture_file(root, image_value, "image", name)
                    if image_value is not None
                    else None
                ),
                hypothesis=(
                    _fixture_file(root, hypothesis_value, "hypothesis", name)
                    if hypothesis_value is not None
                    else None
                ),
            )
        )
    return cases


def _read_text(path: Path, label: str) -> str:
    try:
        # Windows editors often add a BOM; it is an encoding marker, not text,
        # so it must not count as a recognition error.
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise BenchmarkError(f"The {label} text cannot be read: {exc}") from exc


def run_cases(
    cases: Sequence[BenchmarkCase],
    *,
    ocr_runner: Callable[[Path, list[str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score every case, keeping a failure from hiding the others.

    A missing language file, an unavailable engine or a damaged image is
    reported for that case only, so one broken fixture does not discard a whole
    run. Failed cases are excluded from the totals and counted in ``errors``.
    """
    runner = ocr_runner or ocr_service.extract_image_text
    results: list[dict[str, Any]] = []
    for case in cases:
        result: dict[str, Any] = {
            "name": case.name,
            "category": case.category,
            "languages": list(case.languages),
            "source": case.source,
        }
        try:
            reference = _read_text(case.reference, "reference")
        except BenchmarkError as exc:
            results.append({**result, "error": str(exc)})
            continue

        if case.image is not None:
            try:
                output = runner(case.image, list(case.languages))
            except AppError as exc:
                results.append(
                    {**result, "error": exc.message, "error_code": exc.code}
                )
                continue
            hypothesis = str(output.get("text") or "")
            result["engine"] = output.get("engine")
            result["engine_version"] = output.get("engine_version")
            result["confidence"] = output.get("confidence")
        else:
            if case.hypothesis is None:  # pragma: no cover - load_manifest guarantees one
                results.append(
                    {**result, "error": "The case has no image or transcript to score."}
                )
                continue
            try:
                hypothesis = _read_text(case.hypothesis, "hypothesis")
            except BenchmarkError as exc:
                results.append({**result, "error": str(exc)})
                continue

        result.update(score_text(reference, hypothesis))
        results.append(result)

    scored = [result for result in results if "error" not in result]
    categories: list[dict[str, Any]] = []
    for category in dict.fromkeys(result["category"] for result in scored):
        members = [result for result in scored if result["category"] == category]
        categories.append({"category": category, **_aggregate(members)})
    return {
        "cases": results,
        "categories": categories,
        "overall": _aggregate(scored),
        "errors": len(results) - len(scored),
    }


def _format_rate(value: float, reference_units: int) -> str:
    if reference_units == 0:
        return "n/a"
    return f"{value * 100:.2f}%"


def _configure_output() -> None:
    """Print UTF-8 even when the console would reject Burmese case names.

    A Windows console redirected to a file or pipe can default to a legacy code
    page, and a Burmese name would then raise instead of being reported.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):  # pragma: no cover - platform dependent
            pass


def _rate_columns(entry: dict[str, Any]) -> tuple[str, str]:
    return (
        _format_rate(entry["character_error_rate"], entry["reference_characters"]),
        _format_rate(entry["word_error_rate"], entry["reference_words"]),
    )


def _print_report(report: dict[str, Any]) -> None:
    name_width = max([len("Case"), *(len(case["name"]) for case in report["cases"])])
    header = (
        f"{'Case'.ljust(name_width)}  {'Category':<14}  {'CER':>8}  {'WER':>8}"
        f"  {'Chars':>7}  Source"
    )
    print("Local OCR accuracy benchmark")
    print(header)
    print("-" * len(header))
    for case in report["cases"]:
        if "error" in case:
            print(
                f"{case['name'].ljust(name_width)}  {case['category']:<14}"
                f"  {'-':>8}  {'-':>8}  {'-':>7}  error: {case['error']}"
            )
            continue
        cer, wer = _rate_columns(case)
        print(
            f"{case['name'].ljust(name_width)}  {case['category']:<14}"
            f"  {cer:>8}  {wer:>8}"
            f"  {case['reference_characters']:>7}  {case['source']}"
        )

    if report["categories"]:
        print()
        print("By category (weighted by reference length)")
        for category in report["categories"]:
            cer, wer = _rate_columns(category)
            print(
                f"  {category['category']:<20}  CER {cer:>8}  WER {wer:>8}"
                f"  ({category['cases']} case(s))"
            )

    overall = report["overall"]
    cer, wer = _rate_columns(overall)
    print()
    print(f"Overall: {overall['cases']} case(s), CER {cer}, WER {wer}")
    if report["errors"]:
        print(
            f"{report['errors']} case(s) could not be scored and are excluded from the totals."
        )


def main(argv: Sequence[str] | None = None) -> int:
    _configure_output()
    parser = argparse.ArgumentParser(
        prog="python -m app.ocr_benchmark",
        description=(
            "Score local OCR output against checked reference text with CER and WER."
        ),
    )
    parser.add_argument(
        "fixtures",
        type=Path,
        help=f"Folder containing {MANIFEST_NAME} and the reference transcripts.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="names",
        metavar="NAME",
        help="Only run this case. Repeat the option to run several.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full report as JSON instead of a table.",
    )
    parser.add_argument(
        "--segmentation-mode",
        type=int,
        choices=ocr_service.PAGE_SEGMENTATION_MODES,
        default=None,
        metavar="MODE",
        help=(
            "Tesseract page segmentation mode (3 automatic, 4 single column, "
            "6 single block, 11 sparse text). Defaults to the configured value."
        ),
    )
    args = parser.parse_args(argv)

    try:
        cases = load_manifest(args.fixtures)
    except BenchmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.names:
        known = {case.name for case in cases}
        unknown = sorted(set(args.names) - known)
        if unknown:
            print(
                f"error: unknown case(s): {', '.join(unknown)}",
                file=sys.stderr,
            )
            return 2
        wanted = set(args.names)
        cases = [case for case in cases if case.name in wanted]

    if args.segmentation_mode is None:
        report = run_cases(cases)
    else:
        mode = args.segmentation_mode

        def runner(path: Path, languages: list[str]) -> dict[str, Any]:
            return ocr_service.extract_image_text(
                path, languages, page_segmentation_mode=mode
            )

        report = run_cases(cases, ocr_runner=runner)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
