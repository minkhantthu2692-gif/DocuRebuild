from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_local_database(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["projects"] == 0


def test_meta_is_honest_about_available_capabilities(client: TestClient) -> None:
    body = client.get("/api/meta").json()
    capabilities = body["capabilities"]
    assert capabilities["import_images"] is True
    assert capabilities["image_transform"] is True
    # Not yet implemented; must not be advertised.
    assert capabilities["import_pdf"] is False
    assert capabilities["ocr"] is False
    assert capabilities["ai"] is False
    assert capabilities["export"] is False


def test_meta_exposes_import_limits(client: TestClient) -> None:
    body = client.get("/api/meta").json()
    assert body["max_import_mb"] == 200
    assert body["max_upload_batch"] == 50
