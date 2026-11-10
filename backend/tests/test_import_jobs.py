from __future__ import annotations

import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.db.project_schema import project_db
from app.services import pdf as pdf_service
from tests.conftest import make_png
from tests.test_pdf import make_pdf


def wait_for_job(
    client: TestClient,
    project_id: str,
    job_id: str,
    *,
    timeout: float = 40.0,
) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/projects/{project_id}/imports/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"succeeded", "failed", "cancelled"}:
            return last
        time.sleep(0.02)
    raise AssertionError(f"Import job did not finish in time: {last}")


def start_job(client: TestClient, project_id: str, files: list[tuple]) -> dict:
    response = client.post(f"/api/projects/{project_id}/imports", files=files)
    assert response.status_code == 202, response.text
    return response.json()


def test_import_job_reports_progress_and_completes(
    client: TestClient, project: dict
) -> None:
    project_id = project["id"]
    job = start_job(
        client,
        project_id,
        [
            ("files", ("ဓာတ်ပုံ.png", make_png(), "image/png")),
            (
                "files",
                ("အခန်း-၃.pdf", make_pdf(["One", "Two", "Three"]), "application/pdf"),
            ),
        ],
    )
    assert job["kind"] == "pages_import"
    assert job["file_count"] == 2
    assert job["filenames"] == ["ဓာတ်ပုံ.png", "အခန်း-၃.pdf"]
    assert job["total_pages"] == 4

    finished = wait_for_job(client, project_id, job["id"])
    assert finished["status"] == "succeeded", finished
    assert finished["progress"] == 1.0
    assert finished["imported_pages"] == 4
    assert finished["current_file"] is None
    assert finished["error"] is None
    assert finished["completed_at"]

    pages = client.get(f"/api/projects/{project_id}/pages").json()
    assert [page["page_number"] for page in pages] == [1, 2, 3, 4]
    assert pages[0]["original_filename"] == "ဓာတ်ပုံ.png"
    assert pages[1]["original_filename"] == "အခန်း-၃.pdf"

    listed = client.get(f"/api/projects/{project_id}/imports").json()
    assert [item["id"] for item in listed] == [job["id"]]

    # A finished job can no longer be cancelled.
    cancelled = client.post(f"/api/projects/{project_id}/imports/{job['id']}/cancel")
    assert cancelled.status_code == 409
    assert cancelled.json()["detail"]["code"] == "import_not_running"


def test_import_job_reports_a_localizable_failure_and_rolls_back(
    client: TestClient, project: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = pdf_service.render_page
    calls = {"count": 0}

    def flaky_render(document, index, dpi):
        calls["count"] += 1
        if index == 1:
            raise AppError(422, "pdf_page_render_failed", "PDF page 2 could not be rendered.")
        return original(document, index, dpi)

    monkeypatch.setattr(pdf_service, "render_page", flaky_render)

    project_id = project["id"]
    job = start_job(
        client,
        project_id,
        [("files", ("broken.pdf", make_pdf(["First", "Second"]), "application/pdf"))],
    )
    finished = wait_for_job(client, project_id, job["id"])

    assert finished["status"] == "failed"
    assert finished["error_code"] == "pdf_page_render_failed"
    assert finished["imported_pages"] == 0
    assert finished["progress"] == 0.0
    assert finished["completed_at"]
    assert client.get(f"/api/projects/{project_id}/pages").json() == []


def test_import_job_rejects_invalid_files_before_creating_a_job(
    client: TestClient, project: dict
) -> None:
    document = pymupdf.open()
    try:
        document.new_page()
        buffer = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner",
            user_pw="secret",
        )
    finally:
        document.close()

    response = client.post(
        f"/api/projects/{project['id']}/imports",
        files=[("files", ("locked.pdf", buffer, "application/pdf"))],
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "pdf_encrypted"
    assert client.get(f"/api/projects/{project['id']}/imports").json() == []


def test_import_job_cancellation_keeps_finished_files_and_rolls_back_current(
    client: TestClient, project: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = pdf_service.render_page

    def slow_render(document, index, dpi):
        time.sleep(0.05)
        return original(document, index, dpi)

    monkeypatch.setattr(pdf_service, "render_page", slow_render)

    project_id = project["id"]
    job = start_job(
        client,
        project_id,
        [
            ("files", ("first.png", make_png(), "image/png")),
            (
                "files",
                ("long.pdf", make_pdf([f"Page {i}" for i in range(1, 41)]), "application/pdf"),
            ),
        ],
    )

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        current = client.get(f"/api/projects/{project_id}/imports/{job['id']}").json()
        if current["imported_pages"] >= 1:
            break
        time.sleep(0.01)
    else:  # pragma: no cover - diagnostic for slow machines
        raise AssertionError("The first file never completed")

    requested = client.post(f"/api/projects/{project_id}/imports/{job['id']}/cancel")
    assert requested.status_code == 200, requested.text
    assert requested.json()["status"] in {"cancelling", "cancelled"}

    finished = wait_for_job(client, project_id, job["id"])
    assert finished["status"] == "cancelled"
    assert finished["imported_pages"] == 1
    assert finished["progress"] == pytest.approx(1 / 41)
    assert finished["current_file"] is None

    pages = client.get(f"/api/projects/{project_id}/pages").json()
    assert len(pages) == 1
    assert pages[0]["original_filename"] == "first.png"


def test_interrupted_job_is_reported_as_failed(client: TestClient, project: dict) -> None:
    project_id = project["id"]
    directory = Path(project["directory"])

    with project_db(directory) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, kind, status, progress, payload, created_at, updated_at,
                              total_pages, imported_pages)
            VALUES ('stale-job', 'pages_import', 'running', 0.4, '{}',
                    '2026-01-01', '2026-01-01', 5, 2)
            """
        )

    response = client.get(f"/api/projects/{project_id}/imports/stale-job")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "import_interrupted"
    assert body["imported_pages"] == 2


def test_import_job_not_found_is_localizable(client: TestClient, project: dict) -> None:
    response = client.get(f"/api/projects/{project['id']}/imports/missing")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "import_job_not_found"
