from __future__ import annotations

import pymupdf
from fastapi.testclient import TestClient

from tests.conftest import make_png
from tests.figure_eval import aggregate, score_boxes
from tests.test_regions import (
    _block,
    _engine_available,
    _fake_result,
    _figure_pdf,
    _figure_proposals,
    _page_artwork_png,
    _run_ocr,
    _upload_pdf,
    _upload_png,
    _vector_figure_pdf,
)


def _scaled(box: tuple[float, float, float, float], scale: float) -> dict[str, float]:
    x, y, width, height = box
    return {
        "x": x * scale,
        "y": y * scale,
        "width": width * scale,
        "height": height * scale,
    }


def _multi_column_figure_pdf(caption: str | None = None) -> bytes:
    """A two-column page with one image figure in the right column."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        for index in range(12):
            page.insert_text((72, 120 + index * 18), f"Left column line {index}.", fontsize=10)
        page.insert_image(pymupdf.Rect(320, 180, 528, 380), stream=make_png(200, 180))
        if caption:
            page.insert_text((320, 400), caption, fontsize=10)
        for index in range(6):
            page.insert_text(
                (320, 440 + index * 18), f"Right column line {index}.", fontsize=10
            )
        return document.tobytes()
    finally:
        document.close()


def _two_figure_pdf() -> bytes:
    """One embedded image figure and one vector chart on the same page."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        page.insert_text((72, 60), "Body text at the top.", fontsize=12)
        page.insert_image(pymupdf.Rect(80, 100, 280, 240), stream=make_png(200, 140))
        black = (0, 0, 0)
        page.draw_line((80, 620), (520, 620), color=black, width=0.8)
        page.draw_line((80, 480), (80, 620), color=black, width=0.8)
        page.draw_rect(
            pymupdf.Rect(120, 560, 180, 620), color=None, fill=(0.2, 0.4, 0.8)
        )
        page.draw_line((120, 580), (300, 520), color=(0.8, 0.1, 0.1), width=1.2)
        return document.tobytes()
    finally:
        document.close()


def test_page_wide_figure_precision_and_recall(
    client: TestClient, project: dict, monkeypatch
) -> None:
    """Measure figure proposals against hand-labelled boxes.

    Ground truth is in PDF points for PDF cases (scaled to the rendered page) and
    in image pixels for raster cases. A proposal counts as a hit at IoU >= 0.5.
    The per-case counts and the micro-averaged precision/recall are printed so a
    failure shows exactly which layout regressed.
    """
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())

    results: list[tuple[str, list[dict], list[dict[str, float]]]] = []

    pdf_cases = [
        ("pdf-image", _figure_pdf(), [(100, 200, 300, 200)]),
        ("pdf-vector-chart", _vector_figure_pdf(), [(120, 360, 180, 140)]),
        (
            "pdf-captioned-image",
            _figure_pdf(caption="Figure 1. Captioned spectrum"),
            [(100, 200, 300, 200)],
        ),
        ("pdf-shaded-backing", _vector_figure_pdf(image=True), [(100, 360, 200, 140)]),
        ("pdf-background", _figure_pdf(background=True), []),
        ("pdf-logo", _figure_pdf(logo=True), []),
        (
            "pdf-multi-column",
            _multi_column_figure_pdf(caption="Figure 5. Right column result"),
            [(320, 180, 208, 200)],
        ),
        (
            "pdf-two-figures",
            _two_figure_pdf(),
            [(80, 100, 200, 140), (120, 520, 180, 100)],
        ),
    ]
    for name, data, truth_points in pdf_cases:
        page = _upload_pdf(client, project["id"], f"{name}.pdf", data)
        body, figures = _figure_proposals(client, project["id"], page["id"])
        scale = body["page_width"] / 600
        truth = [_scaled(box, scale) for box in truth_points]
        results.append((name, figures, truth))

    raster_cases = [
        ("raster-chart", _page_artwork_png(), [(700, 260, 360, 300)]),
        ("raster-text-only", _page_artwork_png(text_only=True), []),
    ]
    for name, data, truth_points in raster_cases:
        monkeypatch.setattr(
            ocr,
            "_perform_ocr",
            lambda *args, **kwargs: _fake_result(
                [_block(1, "paragraph", "Body text.", 90, 90, 450, 100)]
            ),
        )
        page = _upload_png(client, project["id"], f"{name}.png", data)
        _run_ocr(client, project["id"], page["id"])
        _, figures = _figure_proposals(client, project["id"], page["id"])
        truth = [_scaled(box, 1.0) for box in truth_points]
        results.append((name, figures, truth))

    scores = []
    for name, figures, truth in results:
        score = score_boxes(figures, truth)
        scores.append(score)
        if not truth:
            assert figures == [], f"{name}: expected no figures, got {figures}"
        else:
            assert len(figures) == len(truth), (
                f"{name}: expected {len(truth)} figure(s), "
                f"got {len(figures)}: {figures}"
            )

    overall = aggregate(scores)
    print("\nFigure detection precision/recall (IoU >= 0.5)")
    for name, figures, truth in results:
        score = score_boxes(figures, truth)
        print(
            f"  {name:22s} proposed={len(figures)} truth={len(truth)} "
            f"precision={score['precision']:.2f} recall={score['recall']:.2f}"
        )
    print(
        f"  {'OVERALL':22s} TP={overall['true_positive']} "
        f"FP={overall['false_positive']} FN={overall['false_negative']} "
        f"precision={overall['precision']:.2f} recall={overall['recall']:.2f} "
        f"f1={overall['f1']:.2f}"
    )

    assert overall["precision"] >= 0.9
    assert overall["recall"] >= 0.9
