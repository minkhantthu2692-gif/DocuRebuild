from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.services import table_rules


def _save(tmp_path: Path, image: Image.Image, name: str = "crop.png") -> Path:
    path = tmp_path / name
    image.save(path, format="PNG")
    return path


def test_detects_one_stroke_per_drawn_rule(tmp_path: Path) -> None:
    image = Image.new("RGB", (300, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([2, 2, 298, 118], outline="black", width=3)
    draw.line([2, 60, 298, 60], fill="black", width=3)
    draw.line([100, 2, 100, 118], fill="black", width=3)

    horizontals, verticals = table_rules.detect_table_rules(_save(tmp_path, image))

    # A thick stroke is one boundary, not one per scanned row.
    assert [round(position) for position, _start, _end in horizontals] == [3, 60, 117]
    assert [round(position) for position, _start, _end in verticals] == [3, 100, 297]
    for _position, start, end in horizontals:
        assert start <= 4 and end >= 297
    for _position, start, end in verticals:
        assert start <= 4 and end >= 117


def test_ignores_marks_shorter_than_a_table_rule(tmp_path: Path) -> None:
    image = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(image)
    # Both marks are far shorter than the share of the crop a real cell border
    # must span, so they are treated as decoration, not as a grid.
    draw.line([10, 50, 60, 50], fill="black", width=3)
    draw.line([30, 10, 30, 40], fill="black", width=3)

    assert table_rules.detect_table_rules(_save(tmp_path, image)) == ([], [])


def test_returns_nothing_for_a_blank_or_unreadable_crop(tmp_path: Path) -> None:
    blank = Image.new("RGB", (300, 120), "white")

    assert table_rules.detect_table_rules(_save(tmp_path, blank)) == ([], [])

    broken = tmp_path / "broken.png"
    broken.write_text("not an image", encoding="utf-8")
    assert table_rules.detect_table_rules(broken) == ([], [])
