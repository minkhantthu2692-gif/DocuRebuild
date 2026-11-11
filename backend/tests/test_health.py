from __future__ import annotations

from fastapi.testclient import TestClient


def _unavailable_engine() -> dict:
    return {
        "engine": "tesseract",
        "available": False,
        "version": None,
        "command": "tesseract",
        "tessdata_dir": None,
        "languages": [],
        "preferred_languages": [],
        "reason": "not_found",
        "setup_hint": "Install Tesseract.",
    }


def test_health_reports_local_database(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["projects"] == 0


def test_meta_is_honest_about_available_capabilities(
    client: TestClient, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _unavailable_engine())
    body = client.get("/api/meta").json()
    capabilities = body["capabilities"]
    assert capabilities["import_images"] is True
    assert capabilities["import_pdf"] is True
    assert capabilities["image_transform"] is True
    # Not yet implemented; must not be advertised.
    assert capabilities["ocr"] is False
    # The local AI adapter and review workflow exist; a provider and model must
    # still be configured by the user before any AI request can run.
    assert capabilities["ai"] is True
    assert capabilities["export"] is False


def test_meta_advertises_ocr_only_when_engine_is_available(
    client: TestClient, monkeypatch
) -> None:
    from app.services import ocr

    available = {
        **_unavailable_engine(),
        "available": True,
        "version": "5.3.3",
        "languages": ["eng", "mya"],
        "preferred_languages": ["eng", "mya"],
        "reason": None,
        "setup_hint": None,
    }
    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: available)
    body = client.get("/api/meta").json()
    assert body["capabilities"]["ocr"] is True


def test_meta_exposes_import_limits(client: TestClient) -> None:
    body = client.get("/api/meta").json()
    assert body["max_import_mb"] == 200
    assert body["max_upload_batch"] == 50
