from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DOCUREBUILD_DATA_DIR", str(tmp_path / "data"))

    from app.core.config import get_settings
    from app.db.session import dispose_engine

    get_settings.cache_clear()
    dispose_engine()

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    dispose_engine()
    get_settings.cache_clear()


@pytest.fixture()
def project(client: TestClient) -> dict:
    response = client.post(
        "/api/projects",
        json={"name": "Quantum Mechanics", "description": "Reference book"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_png(width: int = 1200, height: int = 800, color: tuple[int, int, int] = (250, 250, 250)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def upload_pages(client: TestClient, project_id: str, names: list[str]) -> list[dict]:
    files = [("files", (name, make_png(), "image/png")) for name in names]
    response = client.post(f"/api/projects/{project_id}/pages/import", files=files)
    assert response.status_code == 200, response.text
    return response.json()
