"""Non-destructive page processing.

A page never loses its immutable source. Processing is described by a small,
validated JSON document stored on the page row and re-applied from the source
whenever the display copy is rebuilt:

    {
      "geometry": [
        {"type": "crop", "rect": {"x": 0.05, "y": 0.02, "width": 0.9, "height": 0.9}},
        {"type": "perspective", "corners": [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0]]},
        {"type": "deskew", "angle": 1.4}
      ],
      "filters": {"grayscale": false, "contrast": 1.0, ...}
    }

Geometry steps run in order and use coordinates normalised against the image
produced by the previous step, so a new crop always refers to what the user is
looking at. Filters always run last. Every operation is reversible: removing a
step (or clearing the spec) re-renders from the source.

Everything here is pure Pillow; no network and no extra native dependency.
"""

from __future__ import annotations

import json
import math
from typing import Any

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from app.core.errors import AppError

MAX_GEOMETRY_STEPS = 24
MIN_NORMALISED_SIZE = 0.02
MAX_DESKEW_ANGLE = 15.0

DEFAULT_FILTERS: dict[str, Any] = {
    "grayscale": False,
    "contrast": 1.0,
    "brightness": 1.0,
    "sharpness": 1.0,
    "denoise": 0,
    "shadow_removal": False,
    "background_cleanup": False,
    "threshold": False,
    "threshold_level": 55,
}


def _invalid(message: str) -> AppError:
    return AppError(400, "invalid_page_edits", message)


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(f"'{field}' must be a number.")
    result = float(value)
    if not math.isfinite(result):
        raise _invalid(f"'{field}' must be a finite number.")
    return result


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise _invalid(f"'{field}' must be true or false.")
    return value


def _normalise_rect(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise _invalid("A crop needs a rectangle.")
    x = _number(value.get("x"), "crop.x")
    y = _number(value.get("y"), "crop.y")
    width = _number(value.get("width"), "crop.width")
    height = _number(value.get("height"), "crop.height")
    if width < MIN_NORMALISED_SIZE or height < MIN_NORMALISED_SIZE:
        raise _invalid("A crop must cover at least 2% of each side.")
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    width = min(width, 1.0 - x)
    height = min(height, 1.0 - y)
    if width < MIN_NORMALISED_SIZE or height < MIN_NORMALISED_SIZE:
        raise _invalid("The crop rectangle is outside the page.")
    return {
        "x": round(x, 4),
        "y": round(y, 4),
        "width": round(width, 4),
        "height": round(height, 4),
    }


def _normalise_corners(value: Any) -> list[list[float]]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise _invalid("A perspective correction needs four corners.")
    corners: list[list[float]] = []
    for index, point in enumerate(value):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise _invalid(f"Corner {index + 1} must be a pair of coordinates.")
        x = max(0.0, min(1.0, _number(point[0], f"corner {index + 1} x")))
        y = max(0.0, min(1.0, _number(point[1], f"corner {index + 1} y")))
        corners.append([round(x, 4), round(y, 4)])

    area = 0.0
    for index in range(4):
        x1, y1 = corners[index]
        x2, y2 = corners[(index + 1) % 4]
        area += x1 * y2 - x2 * y1
    if abs(area) / 2.0 < 0.02:
        raise _invalid("The perspective area is too small.")
    return corners


def _normalise_geometry(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise _invalid("'geometry' must be a list of operations.")
    if len(value) > MAX_GEOMETRY_STEPS:
        raise _invalid(f"Apply at most {MAX_GEOMETRY_STEPS} geometry operations.")

    steps: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise _invalid("Each geometry operation must be an object.")
        kind = raw.get("type")
        if kind == "crop":
            steps.append({"type": "crop", "rect": _normalise_rect(raw.get("rect"))})
        elif kind == "perspective":
            steps.append(
                {"type": "perspective", "corners": _normalise_corners(raw.get("corners"))}
            )
        elif kind == "deskew":
            angle = _number(raw.get("angle"), "deskew.angle")
            if abs(angle) > MAX_DESKEW_ANGLE:
                raise _invalid(f"Straightening is limited to ±{MAX_DESKEW_ANGLE:g} degrees.")
            steps.append({"type": "deskew", "angle": round(angle, 2)})
        else:
            raise _invalid(f"Unknown geometry operation: {kind!r}.")
    return steps


def _normalise_filters(value: Any) -> dict[str, Any]:
    if value is None:
        return dict(DEFAULT_FILTERS)
    if not isinstance(value, dict):
        raise _invalid("'filters' must be an object.")

    filters = dict(DEFAULT_FILTERS)
    if "grayscale" in value:
        filters["grayscale"] = _boolean(value["grayscale"], "filters.grayscale")
    if "shadow_removal" in value:
        filters["shadow_removal"] = _boolean(
            value["shadow_removal"], "filters.shadow_removal"
        )
    if "background_cleanup" in value:
        filters["background_cleanup"] = _boolean(
            value["background_cleanup"], "filters.background_cleanup"
        )
    if "threshold" in value:
        filters["threshold"] = _boolean(value["threshold"], "filters.threshold")

    if "contrast" in value:
        contrast = _number(value["contrast"], "filters.contrast")
        if not 0.5 <= contrast <= 2.5:
            raise _invalid("Contrast must be between 50% and 250%.")
        filters["contrast"] = round(contrast, 2)
    if "brightness" in value:
        brightness = _number(value["brightness"], "filters.brightness")
        if not 0.5 <= brightness <= 1.5:
            raise _invalid("Brightness must be between 50% and 150%.")
        filters["brightness"] = round(brightness, 2)
    if "sharpness" in value:
        sharpness = _number(value["sharpness"], "filters.sharpness")
        if not 0.5 <= sharpness <= 2.5:
            raise _invalid("Sharpness must be between 50% and 250%.")
        filters["sharpness"] = round(sharpness, 2)
    if "denoise" in value:
        denoise = value["denoise"]
        if isinstance(denoise, bool) or not isinstance(denoise, int) or not 0 <= denoise <= 3:
            raise _invalid("Denoise strength must be 0, 1, 2 or 3.")
        filters["denoise"] = denoise
    if "threshold_level" in value:
        level = value["threshold_level"]
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 99:
            raise _invalid("The threshold level must be between 1 and 99.")
        filters["threshold_level"] = level
    return filters


def normalise_edits(payload: Any) -> dict[str, Any]:
    """Validate a client payload and return the canonical edit document."""
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise _invalid("Page edits must be an object.")
    return {
        "geometry": _normalise_geometry(payload.get("geometry")),
        "filters": _normalise_filters(payload.get("filters")),
    }


def decode_edits(raw: str | None) -> dict[str, Any]:
    """Read stored edits defensively; corrupt JSON falls back to no edits."""
    if not raw:
        return normalise_edits({})
    try:
        return normalise_edits(json.loads(raw))
    except (ValueError, TypeError, AppError):
        return normalise_edits({})


def filters_are_neutral(filters: dict[str, Any]) -> bool:
    return all(filters.get(key) == value for key, value in DEFAULT_FILTERS.items())


def has_edits(edits: dict[str, Any]) -> bool:
    geometry = [
        step
        for step in edits.get("geometry", [])
        if not (step.get("type") == "deskew" and abs(float(step.get("angle", 0.0))) < 0.05)
    ]
    return bool(geometry) or not filters_are_neutral(edits.get("filters", {}))


def _fill(filters: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULT_FILTERS, **filters}


def _apply_geometry(image: Image.Image, step: dict[str, Any]) -> Image.Image:
    kind = step["type"]
    width, height = image.size

    if kind == "crop":
        rect = step["rect"]
        left = round(rect["x"] * width)
        top = round(rect["y"] * height)
        right = min(width, round((rect["x"] + rect["width"]) * width))
        bottom = min(height, round((rect["y"] + rect["height"]) * height))
        if right - left < 8 or bottom - top < 8:
            raise _invalid("The crop area is too small to process.")
        return image.crop((left, top, right, bottom))

    if kind == "perspective":
        points = [(x * width, y * height) for x, y in step["corners"]]
        output_width = max(
            math.dist(points[0], points[3]), math.dist(points[1], points[2])
        )
        output_height = max(
            math.dist(points[0], points[1]), math.dist(points[3], points[2])
        )
        target = (max(8, round(output_width)), max(8, round(output_height)))
        data = tuple(value for point in points for value in point)
        return image.transform(
            target,
            Image.Transform.QUAD,
            data=data,
            resample=Image.Resampling.BICUBIC,
        )

    angle = float(step["angle"])
    if abs(angle) < 0.05:
        return image
    return image.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=(255, 255, 255),
    )


def _apply_filters(image: Image.Image, filters: dict[str, Any]) -> Image.Image:
    result = image
    width, height = result.size

    denoise = int(filters["denoise"])
    if denoise:
        result = result.filter(ImageFilter.MedianFilter(size=2 * denoise + 1))

    if filters["shadow_removal"]:
        radius = max(3.0, min(width, height) / 40.0)
        background = result.filter(ImageFilter.GaussianBlur(radius=radius))
        # offset=255 keeps a white page white while darker ink stays dark, which
        # is the cheap Pillow equivalent of dividing by the estimated background.
        result = ImageChops.subtract(result, background, scale=1.0, offset=255)
        result = ImageOps.autocontrast(result, cutoff=1)

    if filters["background_cleanup"]:
        result = ImageOps.autocontrast(result, cutoff=1)

    if filters["grayscale"]:
        result = result.convert("L")

    brightness = float(filters["brightness"])
    if abs(brightness - 1.0) > 0.005:
        result = ImageEnhance.Brightness(result).enhance(brightness)

    contrast = float(filters["contrast"])
    if abs(contrast - 1.0) > 0.005:
        result = ImageEnhance.Contrast(result).enhance(contrast)

    sharpness = float(filters["sharpness"])
    if abs(sharpness - 1.0) > 0.005:
        result = ImageEnhance.Sharpness(result).enhance(sharpness)

    if filters["threshold"]:
        level = int(filters["threshold_level"]) * 255 // 100
        gray = result.convert("L")
        result = gray.point(lambda value: 255 if value >= level else 0).convert("L")

    return result.convert("RGB")


def apply_edits(image: Image.Image, edits: dict[str, Any]) -> Image.Image:
    """Render a source image through the stored edit document."""
    result = image.convert("RGB") if image.mode not in ("RGB", "L") else image
    try:
        for step in edits.get("geometry", []):
            result = _apply_geometry(result, step)
        return _apply_filters(result, _fill(edits.get("filters", {})))
    except AppError:
        raise
    except (OSError, ValueError) as exc:  # pragma: no cover - defensive
        raise AppError(422, "image_process_failed", "The page could not be processed.") from exc


def geometry_without_deskew(edits: dict[str, Any]) -> dict[str, Any]:
    return {
        "geometry": [step for step in edits.get("geometry", []) if step["type"] != "deskew"],
        "filters": dict(DEFAULT_FILTERS),
    }


def _row_profile(image: Image.Image) -> list[float]:
    # Collapsing to one pixel per row turns the projection profile into a cheap
    # list of row means; correctly aligned text lines produce the highest variance.
    profile = image.resize((1, image.height), Image.Resampling.BOX)
    return [float(value) for value in profile.getdata()]


def _variance(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _score_angle(gray: Image.Image, angle: float) -> float:
    rotated = gray.rotate(
        angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=255
    )
    return _variance(_row_profile(rotated))


def estimate_skew_angle(image: Image.Image, max_angle: float = 10.0) -> float:
    """Estimate the rotation needed to straighten the page, in degrees."""
    gray = ImageOps.grayscale(image)
    if gray.width > 320:
        ratio = 320 / gray.width
        gray = gray.resize(
            (320, max(1, round(gray.height * ratio))), Image.Resampling.LANCZOS
        )
    if gray.height < 16 or gray.width < 16:
        return 0.0

    coarse_step = 1.5
    steps = int(max_angle / coarse_step)
    coarse = [round(-max_angle + index * coarse_step, 2) for index in range(steps * 2 + 1)]
    best = max(coarse, key=lambda angle: _score_angle(gray, angle))

    fine_step = 0.25
    fine = [
        round(best + index * fine_step, 2)
        for index in range(-int(coarse_step / fine_step), int(coarse_step / fine_step) + 1)
    ]
    best = max(fine, key=lambda angle: _score_angle(gray, angle))

    if abs(best) < 0.2:
        return 0.0
    return round(max(-max_angle, min(max_angle, best)), 1)
