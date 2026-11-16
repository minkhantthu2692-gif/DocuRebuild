from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.services import artwork


def _page(path: Path, draw, color: tuple[int, int, int] = (252, 252, 252)) -> Path:
    image = Image.new("RGB", (1200, 800), color)
    draw(ImageDraw.Draw(image))
    image.save(path)
    return path


def _text_and_chart(draw: ImageDraw.ImageDraw) -> None:
    for y in range(100, 180, 26):
        draw.rectangle((100, y, 520, y + 10), fill=(30, 30, 30))
    draw.line((700, 560, 1060, 560), fill=(20, 20, 20), width=2)
    draw.line((700, 260, 700, 560), fill=(20, 20, 20), width=2)
    for x, top in ((740, 420), (800, 340), (860, 260)):
        draw.rectangle((x, top, x + 34, 560), fill=(40, 80, 160))
    draw.line((700, 440, 1060, 300), fill=(160, 40, 40), width=3)


def test_artwork_regions_find_uncaptioned_ink_outside_the_text_layout(
    tmp_path: Path,
) -> None:
    path = _page(tmp_path / "page.png", _text_and_chart)

    regions = artwork.artwork_regions(
        path,
        [{"x": 90, "y": 90, "width": 450, "height": 100}],
        1200,
        800,
    )

    assert len(regions) == 1
    box = regions[0]
    # Separate bars, the axis and the trend line are joined into one drawing.
    assert abs(box["x"] - 700) <= 20
    assert abs(box["y"] - 260) <= 20
    assert abs(box["x"] + box["width"] - 1060) <= 30
    assert abs(box["y"] + box["height"] - 560) <= 30
    # The OCR paragraph is explained as text, so its ink is never a figure.
    assert box["y"] > 200


def test_artwork_regions_ignore_rules_frames_and_blank_pages(tmp_path: Path) -> None:
    def decor(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle((10, 10, 1190, 790), outline=(20, 20, 20), width=2)
        draw.line((60, 400, 1140, 400), fill=(20, 20, 20), width=1)

    path = _page(tmp_path / "decor.png", decor)
    assert artwork.artwork_regions(path, [], 1200, 800) == []

    blank = _page(tmp_path / "blank.png", lambda draw: None)
    assert artwork.artwork_regions(blank, [], 1200, 800) == []


def test_artwork_regions_skip_a_dark_page(tmp_path: Path) -> None:
    def block(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle((300, 300, 900, 600), fill=(200, 200, 200))

    path = _page(tmp_path / "dark.png", block, color=(40, 40, 40))

    # A dark page cannot be separated from its content, so it is not analysed
    # instead of proposing the whole page as artwork.
    assert artwork.artwork_regions(path, [], 1200, 800) == []


def test_artwork_regions_return_nothing_for_an_unreadable_image(tmp_path: Path) -> None:
    assert artwork.artwork_regions(tmp_path / "missing.png", [], 1200, 800) == []

    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    assert artwork.artwork_regions(broken, [], 1200, 800) == []
