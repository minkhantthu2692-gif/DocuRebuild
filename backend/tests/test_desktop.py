from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-desktop-token"


@pytest.fixture()
def desktop_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text(
        "<!doctype html><title>DocuRebuild</title><div id=root></div>",
        encoding="utf-8",
    )
    (web / "assets" / "app.js").write_text("console.log('app');", encoding="utf-8")

    monkeypatch.setenv("DOCUREBUILD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DOCUREBUILD_API_TOKEN", TOKEN)
    monkeypatch.setenv("DOCUREBUILD_WEB_DIST", str(web))

    from app.core.config import get_settings
    from app.db.session import dispose_engine
    from app.services.imports import shutdown_import_executor
    from app.services.ocr import clear_engine_cache, shutdown_ocr_executor

    get_settings.cache_clear()
    dispose_engine()
    clear_engine_cache()

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    shutdown_import_executor()
    shutdown_ocr_executor()
    clear_engine_cache()
    dispose_engine()
    get_settings.cache_clear()


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_api_requires_the_launch_token(desktop_client: TestClient) -> None:
    response = desktop_client.get("/api/health")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_api_rejects_a_wrong_token(desktop_client: TestClient) -> None:
    response = desktop_client.get(
        "/api/health", headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


def test_api_accepts_the_launch_token(desktop_client: TestClient) -> None:
    response = desktop_client.get("/api/health", headers=_auth())
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_the_built_client_is_served_from_the_same_origin(
    desktop_client: TestClient,
) -> None:
    root = desktop_client.get("/", headers=_auth())
    assert root.status_code == 200
    assert "DocuRebuild" in root.text

    route = desktop_client.get("/settings", headers=_auth())
    assert route.status_code == 200
    assert "DocuRebuild" in route.text

    asset = desktop_client.get("/assets/app.js", headers=_auth())
    assert asset.status_code == 200
    assert "console.log" in asset.text


def test_unknown_api_paths_do_not_fall_back_to_the_client(
    desktop_client: TestClient,
) -> None:
    response = desktop_client.get("/api/does-not-exist", headers=_auth())
    assert response.status_code == 404
    assert "DocuRebuild" not in response.text


def test_the_client_asset_path_cannot_escape_the_dist_folder(
    desktop_client: TestClient,
) -> None:
    response = desktop_client.get("/..%2F..%2Fsecret.txt", headers=_auth())
    assert response.status_code == 404


def test_desktop_server_only_accepts_loopback() -> None:
    from desktop_server import _parse_args

    assert _parse_args(["--port", "8123"]).host == "127.0.0.1"
    with pytest.raises(SystemExit):
        _parse_args(["--port", "8123", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        _parse_args(["--port", "70000"])


def test_the_token_is_not_part_of_the_client_bundle(
    desktop_client: TestClient, tmp_path: Path
) -> None:
    index = desktop_client.get("/", headers=_auth())
    assert TOKEN not in index.text
    assert TOKEN not in (tmp_path / "web" / "assets" / "app.js").read_text(
        encoding="utf-8"
    )
