from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import make_png, upload_pages


def test_import_creates_pages_thumbnails_and_immutable_sources(
    client: TestClient, project: dict
) -> None:
    pages = upload_pages(client, project["id"], ["page-1.png", "page-2.png"])
    assert [page["page_number"] for page in pages] == [1, 2]
    assert all(page["status"] == "ready" for page in pages)
    assert pages[0]["width"] == 1200
    assert pages[0]["original_asset_id"]

    thumbnail = client.get(
        f"/api/projects/{project['id']}/assets/{pages[0]['thumbnail_asset_id']}/file"
    )
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"

    original = client.get(
        f"/api/projects/{project['id']}/assets/{pages[0]['original_asset_id']}/file"
    )
    assert original.status_code == 200
    assert original.content == make_png()

    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["page_count"] == 2


def test_unsupported_file_is_rejected(client: TestClient, project: dict) -> None:
    response = client.post(
        f"/api/projects/{project['id']}/pages/import",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_file_type"


def test_rotate_page_creates_reversible_display_copy(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    page = upload_pages(client, project_id, ["scan.png"])[0]
    page_id = page["id"]

    rotated = client.post(
        f"/api/projects/{project_id}/pages/{page_id}/rotate", json={"degrees": 90}
    )
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert body["rotation"] == 90
    assert body["width"] == 800
    assert body["height"] == 1200
    assert body["display_asset_id"]

    display = client.get(
        f"/api/projects/{project_id}/assets/{body['display_asset_id']}/file"
    )
    assert display.status_code == 200
    assert display.headers["content-type"] == "image/png"

    restored = client.post(
        f"/api/projects/{project_id}/pages/{page_id}/rotate", json={"degrees": 270}
    ).json()
    assert restored["rotation"] == 0
    assert restored["display_asset_id"] is None
    assert restored["width"] == 1200


def test_reorder_and_delete_pages(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    pages = upload_pages(client, project_id, ["a.png", "b.png", "c.png"])
    ids = [page["id"] for page in pages]

    reordered = client.put(
        f"/api/projects/{project_id}/pages/order",
        json={"page_ids": [ids[2], ids[0], ids[1]]},
    )
    assert reordered.status_code == 200
    assert [page["page_number"] for page in reordered.json()] == [1, 2, 3]
    assert [page["id"] for page in reordered.json()] == [ids[2], ids[0], ids[1]]

    invalid = client.put(
        f"/api/projects/{project_id}/pages/order", json={"page_ids": [ids[0]]}
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "invalid_page_order"

    deleted = client.delete(f"/api/projects/{project_id}/pages/{ids[0]}")
    assert deleted.status_code == 200

    remaining = client.get(f"/api/projects/{project_id}/pages").json()
    assert [page["page_number"] for page in remaining] == [1, 2]
    assert {page["id"] for page in remaining} == {ids[1], ids[2]}
