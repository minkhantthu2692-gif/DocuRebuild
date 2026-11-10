from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from tests.conftest import make_png, upload_pages
from tests.test_pdf import make_pdf, upload_pdf


def decode(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def crop_edits(**rect: float) -> dict:
    return {"geometry": [{"type": "crop", "rect": rect}]}


def test_crop_creates_reversible_display_copy_without_touching_source(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["scan.png"])[0]

    response = client.patch(
        f"/api/projects/{project_id}/pages/{page['id']}/edits",
        json={"edits": crop_edits(x=0.25, y=0.25, width=0.5, height=0.5)},
    )
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["width"] == 600
    assert edited["height"] == 400
    assert edited["edits"]["geometry"][0]["type"] == "crop"
    assert edited["display_asset_id"] != page["display_asset_id"]

    display = client.get(
        f"/api/projects/{project_id}/assets/{edited['display_asset_id']}/file"
    )
    assert display.status_code == 200
    assert decode(display.content).size == (600, 400)

    # The immutable source is byte-identical after processing.
    original = client.get(
        f"/api/projects/{project_id}/assets/{page['original_asset_id']}/file"
    )
    assert original.content == make_png()

    reset = client.post(
        f"/api/projects/{project_id}/pages/{page['id']}/edits/reset"
    )
    assert reset.status_code == 200, reset.text
    restored = reset.json()
    assert restored["width"] == 1200
    assert restored["height"] == 800
    assert restored["edits"]["geometry"] == []
    assert restored["display_asset_id"] is None


def test_filters_and_straightening_are_recorded_and_rendered(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["page.png"])[0]

    response = client.patch(
        f"/api/projects/{project_id}/pages/{page['id']}/edits",
        json={
            "edits": {
                "geometry": [{"type": "deskew", "angle": 2.5}],
                "filters": {
                    "grayscale": True,
                    "contrast": 1.4,
                    "denoise": 1,
                    "threshold": True,
                    "threshold_level": 60,
                },
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["edits"]["filters"]["grayscale"] is True
    assert body["edits"]["filters"]["threshold_level"] == 60
    assert body["edits"]["geometry"][0]["angle"] == 2.5
    assert body["width"] == 1200
    assert body["height"] == 800

    display = client.get(
        f"/api/projects/{project_id}/assets/{body['display_asset_id']}/file"
    )
    assert display.status_code == 200
    processed = decode(display.content)
    # A thresholded page collapses to black and white only.
    colours = processed.convert("L").getcolors(maxcolors=8)
    assert colours is not None
    assert {value for _, value in colours} <= {0, 255}


def test_invalid_edits_are_rejected_without_changing_the_page(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["scan.png"])[0]

    too_small = client.patch(
        f"/api/projects/{project_id}/pages/{page['id']}/edits",
        json={"edits": crop_edits(x=0.1, y=0.1, width=0.0, height=0.5)},
    )
    assert too_small.status_code == 400
    assert too_small.json()["detail"]["code"] == "invalid_page_edits"

    unknown = client.patch(
        f"/api/projects/{project_id}/pages/{page['id']}/edits",
        json={"edits": {"geometry": [{"type": "sharpen_everything"}]}},
    )
    assert unknown.status_code == 400
    assert unknown.json()["detail"]["code"] == "invalid_page_edits"

    unchanged = client.get(f"/api/projects/{project_id}/pages").json()[0]
    assert unchanged["edits"]["geometry"] == []
    assert unchanged["display_asset_id"] is None


def test_perspective_and_rotation_compose_on_image_pages(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["scan.png"])[0]

    perspective = client.patch(
        f"/api/projects/{project_id}/pages/{page['id']}/edits",
        json={
            "edits": {
                "geometry": [
                    {
                        "type": "perspective",
                        "corners": [
                            [0.1, 0.1],
                            [0.1, 0.9],
                            [0.9, 0.9],
                            [0.9, 0.1],
                        ],
                    }
                ]
            }
        },
    )
    assert perspective.status_code == 200, perspective.text
    assert perspective.json()["width"] == 960
    assert perspective.json()["height"] == 640

    rotated = client.post(
        f"/api/projects/{project_id}/pages/{page['id']}/rotate", json={"degrees": 90}
    )
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert body["rotation"] == 90
    assert body["width"] == 640
    assert body["height"] == 960
    # Rotation keeps the stored processing steps instead of discarding them.
    assert body["edits"]["geometry"][0]["type"] == "perspective"


def test_pdf_edits_rerender_from_the_original_and_mark_embedded_text_stale(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pdf(client, project_id, "book.pdf", make_pdf(["Hello PDF page"]))[0]
    run = client.get(f"/api/projects/{project_id}/pages/{page['id']}/ocr").json()
    assert run["stale"] is False

    edited = client.patch(
        f"/api/projects/{project_id}/pages/{page['id']}/edits",
        json={"edits": crop_edits(x=0.1, y=0.1, width=0.8, height=0.8)},
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["display_asset_id"] != page["display_asset_id"]
    assert body["width"] < page["width"]

    stale = client.get(f"/api/projects/{project_id}/pages/{page['id']}/ocr").json()
    assert stale["id"] == run["id"]
    assert stale["stale"] is True

    restored = client.post(
        f"/api/projects/{project_id}/pages/{page['id']}/edits/reset"
    ).json()
    assert restored["display_asset_id"]
    assert restored["width"] == page["width"]


def test_base_preview_shows_the_unprocessed_page(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["scan.png"])[0]
    client.patch(
        f"/api/projects/{project_id}/pages/{page['id']}/edits",
        json={"edits": crop_edits(x=0.25, y=0.25, width=0.5, height=0.5)},
    )

    preview = client.get(
        f"/api/projects/{project_id}/pages/{page['id']}/edits/base"
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert decode(preview.content).size == (1200, 800)


def test_deskew_estimate_reports_the_correction_angle(
    client: TestClient, project: dict
) -> None:
    image = Image.new("L", (600, 800), 255)
    draw = ImageDraw.Draw(image)
    for y in range(40, 760, 24):
        draw.rectangle((40, y, 560, y + 8), fill=20)
    skewed = image.rotate(5, expand=False, fillcolor=255, resample=Image.BICUBIC)
    buffer = io.BytesIO()
    skewed.save(buffer, format="PNG")

    project_id = project["id"]
    response = client.post(
        f"/api/projects/{project_id}/pages/import",
        files=[("files", ("skewed.png", buffer.getvalue(), "image/png"))],
    )
    assert response.status_code == 200, response.text
    page = response.json()[0]

    estimate = client.get(
        f"/api/projects/{project_id}/pages/{page['id']}/deskew-estimate"
    )
    assert estimate.status_code == 200, estimate.text
    assert abs(estimate.json()["angle"] + 5) <= 1.0


def test_edits_survive_reopening_the_project(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["scan.png"])[0]
    client.patch(
        f"/api/projects/{project_id}/pages/{page['id']}/edits",
        json={"edits": crop_edits(x=0.0, y=0.0, width=0.5, height=0.5)},
    )

    reopened = client.get(f"/api/projects/{project_id}/pages").json()[0]
    stored = json.dumps(reopened["edits"], sort_keys=True)
    assert "crop" in stored
    assert reopened["width"] == 600
