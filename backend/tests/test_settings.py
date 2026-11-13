from __future__ import annotations

from fastapi.testclient import TestClient


def test_default_settings(client: TestClient) -> None:
    settings = client.get("/api/settings").json()
    assert settings["language"] == "en"
    assert settings["appearance"]["theme"] == "system"
    assert settings["appearance"]["accent"] == "indigo"
    assert settings["editor"]["document_font"] == "serif"
    assert settings["backups"] == {
        "auto_on_open": False,
        "interval_hours": 24,
        "keep_copies": 5,
    }


def test_partial_settings_update_persists(client: TestClient) -> None:
    response = client.patch(
        "/api/settings",
        json={"appearance": {"theme": "dark"}, "language": "my"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["appearance"]["theme"] == "dark"
    assert body["appearance"]["accent"] == "indigo"
    assert body["language"] == "my"

    assert client.get("/api/settings").json()["appearance"]["theme"] == "dark"


def test_invalid_settings_are_rejected(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"language": "klingon"})
    assert response.status_code == 422

    response = client.patch("/api/settings", json={"appearance": {"accent": "neon"}})
    assert response.status_code == 422

    response = client.patch("/api/settings", json={"backups": {"keep_copies": 0}})
    assert response.status_code == 422

    response = client.patch("/api/settings", json={"backups": {"interval_hours": 0}})
    assert response.status_code == 422
