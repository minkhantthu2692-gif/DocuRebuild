from __future__ import annotations

import subprocess
import time

from fastapi.testclient import TestClient

from tests.conftest import upload_pages


def _engine_available(languages: list[str] | None = None) -> dict:
    installed = languages or ["eng", "mya"]
    return {
        "engine": "tesseract",
        "available": True,
        "version": "5.3.3",
        "command": "tesseract",
        "tessdata_dir": None,
        "languages": installed,
        "preferred_languages": [code for code in ("eng", "mya") if code in installed],
        "reason": None,
        "setup_hint": None,
    }


def _engine_unavailable() -> dict:
    return {
        "engine": "tesseract",
        "available": False,
        "version": None,
        "command": "tesseract",
        "tessdata_dir": None,
        "languages": [],
        "preferred_languages": [],
        "reason": "not_found",
        "setup_hint": "Install Tesseract locally.",
    }


def _fake_result() -> dict:
    return {
        "engine_version": "5.3.3",
        "text": "Chapter One\n\nA local OCR result.",
        "mean_confidence": 91.5,
        "blocks": [
            {
                "block_index": 1,
                "kind": "heading",
                "text": "Chapter One",
                "confidence": 96.0,
                "x": 20,
                "y": 30,
                "width": 240,
                "height": 40,
                "line_count": 1,
                "word_count": 2,
            },
            {
                "block_index": 2,
                "kind": "paragraph",
                "text": "A local OCR result.",
                "confidence": 87.0,
                "x": 20,
                "y": 100,
                "width": 360,
                "height": 60,
                "line_count": 2,
                "word_count": 4,
            },
        ],
    }


def _wait_for_run(
    client: TestClient, project_id: str, page_id: str, timeout: float = 5.0
) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/projects/{project_id}/pages/{page_id}/ocr")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest and latest["status"] in {"succeeded", "failed"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"OCR run did not finish: {latest}")


def test_ocr_capabilities_reports_unavailable_engine(
    client: TestClient, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_unavailable())
    body = client.get("/api/ocr/capabilities").json()
    assert body["engine"] == "tesseract"
    assert body["available"] is False
    assert body["reason"] == "not_found"
    assert body["languages"] == []


def test_ocr_run_persists_blocks_and_marks_stale_after_rotation(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_perform_ocr", lambda *args, **kwargs: _fake_result())

    page = upload_pages(client, project["id"], ["ocr-page.png"])[0]
    response = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 202, response.text
    queued = response.json()
    assert queued["page_id"] == page["id"]
    assert queued["status"] in {"queued", "running"}

    run = _wait_for_run(client, project["id"], page["id"])
    assert run["status"] == "succeeded", run
    assert run["engine"] == "tesseract"
    assert run["engine_version"] == "5.3.3"
    assert run["languages"] == ["eng"]
    assert run["mean_confidence"] == 91.5
    assert run["text"] == "Chapter One\n\nA local OCR result."
    assert run["stale"] is False
    assert [block["kind"] for block in run["blocks"]] == ["heading", "paragraph"]
    assert run["blocks"][0]["verified"] is False
    assert run["blocks"][0]["corrected"] is False

    rotated = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/rotate",
        json={"degrees": 90},
    )
    assert rotated.status_code == 200
    latest = client.get(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr"
    ).json()
    assert latest["stale"] is True


def test_ocr_block_corrections_persist_and_reset_verification(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(ocr, "_perform_ocr", lambda *args, **kwargs: _fake_result())

    page = upload_pages(client, project["id"], ["ocr-edit.png"])[0]
    client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr",
        json={"languages": ["eng"]},
    )
    run = _wait_for_run(client, project["id"], page["id"])
    block = run["blocks"][0]

    verified = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr/blocks/{block['id']}",
        json={"verified": True},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["blocks"][0]["verified"] is True

    corrected = client.patch(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr/blocks/{block['id']}",
        json={"text": "Chapter One (corrected)"},
    )
    assert corrected.status_code == 200, corrected.text
    body = corrected.json()
    assert body["blocks"][0]["text"] == "Chapter One (corrected)"
    assert body["blocks"][0]["corrected"] is True
    assert body["blocks"][0]["verified"] is False
    assert body["text"].startswith("Chapter One (corrected)")


def test_ocr_rejects_missing_language_data(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(
        ocr, "detect_engine", lambda force=False: _engine_available(["eng"])
    )
    page = upload_pages(client, project["id"], ["ocr-lang.png"])[0]
    response = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr",
        json={"languages": ["mya"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_language_unavailable"


def test_ocr_rejects_when_engine_is_unavailable(
    client: TestClient, project: dict, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_unavailable())
    page = upload_pages(client, project["id"], ["ocr-off.png"])[0]
    response = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ocr_unavailable"


def test_ocr_fails_when_engine_returns_unstructured_output(
    client: TestClient, project: dict, monkeypatch
) -> None:
    import subprocess

    from app.services import ocr

    monkeypatch.setattr(ocr, "detect_engine", lambda force=False: _engine_available())
    monkeypatch.setattr(
        ocr,
        "_run_command",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="UREBUILD\n", stderr=""
        ),
    )

    page = upload_pages(client, project["id"], ["ocr-plain.png"])[0]
    response = client.post(
        f"/api/projects/{project['id']}/pages/{page['id']}/ocr",
        json={"languages": ["eng"]},
    )
    assert response.status_code == 202, response.text

    run = _wait_for_run(client, project["id"], page["id"])
    assert run["status"] == "failed", run
    assert run["error_code"] == "ocr_failed"
    assert "structured text" in (run["error"] or "")
    assert run["blocks"] == []


def test_parse_version_accepts_common_tesseract_output() -> None:
    from app.services import ocr

    assert (
        ocr._parse_version("tesseract v5.4.0.20240606\n leptonica-1.84.1")
        == "5.4.0.20240606"
    )
    assert ocr._parse_version("tesseract 5.3.3") == "5.3.3"
    assert ocr._parse_version("not a tesseract banner") is None


def test_engine_candidates_prefer_configured_command_and_dedupe(
    monkeypatch, tmp_path
) -> None:
    from app.services import ocr

    installed = str(tmp_path / "Tesseract-OCR" / "tesseract.exe")

    class _Settings:
        tesseract_cmd = installed

    monkeypatch.setattr(ocr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        ocr,
        "_auto_detect_commands",
        lambda: [installed, "/usr/bin/tesseract"],
    )

    candidates = ocr._engine_candidates()
    assert candidates[0] == ("configured", [installed])
    assert candidates[1:] == [("detected", ["/usr/bin/tesseract"])]


def test_detect_engine_falls_back_to_auto_detected_command(
    client: TestClient, monkeypatch
) -> None:
    from app.services import ocr

    detected = "C:/Program Files/Tesseract-OCR/tesseract.exe"
    monkeypatch.setattr(
        ocr,
        "_engine_candidates",
        lambda: [("configured", ["tesseract"]), ("detected", [detected])],
    )

    calls: list[str] = []

    def fake_run(args, timeout):
        calls.append(args[0])
        if args[0] == "tesseract":
            raise FileNotFoundError(args[0])
        if "--version" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                "tesseract v5.4.0.20240606\n leptonica-1.84.1",
                "",
            )
        return subprocess.CompletedProcess(
            args,
            0,
            "List of available languages in tessdata (2):\neng\nosd\n",
            "",
        )

    monkeypatch.setattr(ocr, "_run_command", fake_run)
    status = ocr.detect_engine(force=True)

    assert status["available"] is True
    assert status["version"] == "5.4.0.20240606"
    assert status["languages"] == ["eng", "osd"]
    assert ocr._command_tokens(status["command"]) == [detected]
    assert calls[0] == "tesseract"
    assert detected in calls


def test_detect_engine_reports_not_found_when_no_candidate_runs(
    client: TestClient, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(
        ocr,
        "_engine_candidates",
        lambda: [("configured", ["tesseract"]), ("detected", ["/opt/tesseract"])],
    )

    def fake_run(args, timeout):
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(ocr, "_run_command", fake_run)
    status = ocr.detect_engine(force=True)

    assert status["available"] is False
    assert status["reason"] == "not_found"
    assert status["setup_hint"]


def test_detect_engine_reports_not_configured_without_candidates(
    client: TestClient, monkeypatch
) -> None:
    from app.services import ocr

    monkeypatch.setattr(ocr, "_engine_candidates", lambda: [])
    status = ocr.detect_engine(force=True)

    assert status["available"] is False
    assert status["reason"] == "not_configured"
    assert status["command"] == "tesseract"
