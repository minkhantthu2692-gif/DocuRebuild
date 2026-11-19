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


def test_measures_a_small_table_inside_a_large_page(tmp_path: Path) -> None:
    image = Image.new("RGB", (1000, 1600), "white")
    draw = ImageDraw.Draw(image)
    # A two-row table that fills only a small part of the page. Its cell borders
    # are far shorter than a page-wide minimum stroke.
    draw.rectangle([500, 800, 620, 860], outline="black", width=2)
    draw.line([500, 830, 620, 830], fill="black", width=2)
    draw.line([560, 800, 560, 860], fill="black", width=2)
    path = _save(tmp_path, image, "page.png")

    assert table_rules.detect_table_rules(path) == ([], [])

    region = (470, 770, 650, 890)
    horizontals, verticals = table_rules.detect_table_rules(path, region=region)

    assert [round(position) for position, _start, _end in horizontals] == [
        801,
        831,
        859,
    ]
    assert [round(position) for position, _start, _end in verticals] == [500, 560, 619]
    for _position, start, end in horizontals:
        assert 496 <= start <= 502 and 618 <= end <= 624
    for _position, start, end in verticals:
        assert 798 <= start <= 804 and 856 <= end <= 862

    # Loading the page once and measuring several regions gives the same rules.
    scan = table_rules.load_scan(path)
    assert scan is not None
    assert table_rules.scan_rules(scan, region) == (horizontals, verticals)


def test_region_keeps_a_page_frame_out_of_the_table(tmp_path: Path) -> None:
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 399, 299], outline="black", width=3)
    draw.rectangle([100, 100, 300, 200], outline="black", width=3)
    draw.line([100, 150, 300, 150], fill="black", width=3)
    draw.line([200, 100, 200, 200], fill="black", width=3)

    horizontals, verticals = table_rules.detect_table_rules(
        _save(tmp_path, image), region=(90, 90, 310, 210)
    )

    # The page frame lies outside the region and must not become a table border.
    for position, _start, _end in horizontals:
        assert 95 <= position <= 205
    for position, _start, _end in verticals:
        assert 95 <= position <= 305
    assert [round(position) for position, _start, _end in horizontals] == [
        101,
        150,
        199,
    ]
