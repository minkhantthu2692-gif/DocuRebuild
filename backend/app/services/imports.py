from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.project_schema import project_db, utc_iso
from app.services import pages as page_service

logger = logging.getLogger(__name__)

JOB_KIND = "pages_import"
ACTIVE_STATUSES = ("queued", "running", "cancelling")
TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")


@dataclass
class _ActiveJob:
    event: threading.Event
    project_dir: Path


_registry: dict[str, _ActiveJob] = {}
_registry_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _now() -> str:
    return utc_iso()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            settings = get_settings()
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.import_max_workers),
                thread_name_prefix="docurebuild-import",
            )
        return _executor


def shutdown_import_executor() -> None:
    """Stop accepting imports and mark in-flight jobs as interrupted."""
    global _executor
    with _executor_lock:
        executor = _executor
        _executor = None
    with _registry_lock:
        jobs = list(_registry.items())
        _registry.clear()
    for job_id, active in jobs:
        _mark_failed(
            active.project_dir,
            job_id,
            "The import was interrupted because the local backend stopped.",
            "import_interrupted",
        )
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)


def _job_payload(row) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload"] or "{}")
    except (TypeError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    total_pages = int(row["total_pages"] or 0)
    imported_pages = int(row["imported_pages"] or 0)
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "progress": float(row["progress"] or 0),
        "total_pages": total_pages,
        "imported_pages": imported_pages,
        "current_file": row["current_file"],
        "file_count": int(payload.get("file_count", 0)),
        "filenames": list(payload.get("filenames", [])),
        "error": row["error"],
        "error_code": row["error_code"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }


def _get_row(conn, job_id: str):
    row = conn.execute(
        "SELECT * FROM jobs WHERE id = ? AND kind = ?", (job_id, JOB_KIND)
    ).fetchone()
    if row is None:
        raise AppError(404, "import_job_not_found", "The import job could not be found.")
    return row


def _recover_if_stale(project_dir: Path, row) -> None:
    """Mark jobs that no live worker owns as interrupted.

    The registry only contains jobs started by this backend process. A job row
    still marked active without a registry entry was interrupted by a restart
    or a crash, so it must not stay "running" forever in the UI.
    """
    if row["status"] not in ACTIVE_STATUSES:
        return
    with _registry_lock:
        active = row["id"] in _registry
    if active:
        return
    _mark_failed(
        project_dir,
        row["id"],
        "The import was interrupted before it finished. Imported pages were kept.",
        "import_interrupted",
    )


def _mark_failed(
    project_dir: Path,
    job_id: str,
    message: str,
    code: str,
    imported_pages: int | None = None,
) -> None:
    try:
        with project_db(project_dir) as conn:
            now = _now()
            if imported_pages is None:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', error = ?, error_code = ?, completed_at = ?,
                        current_file = NULL, updated_at = ?
                    WHERE id = ? AND kind = ?
                    """,
                    (message, code, now, now, job_id, JOB_KIND),
                )
            else:
                row = conn.execute(
                    "SELECT total_pages FROM jobs WHERE id = ? AND kind = ?",
                    (job_id, JOB_KIND),
                ).fetchone()
                total = int(row["total_pages"] or 0) if row is not None else 0
                progress = min(1.0, imported_pages / total) if total else 0.0
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', error = ?, error_code = ?, completed_at = ?,
                        current_file = NULL, imported_pages = ?, progress = ?, updated_at = ?
                    WHERE id = ? AND kind = ?
                    """,
                    (
                        message,
                        code,
                        now,
                        imported_pages,
                        progress,
                        now,
                        job_id,
                        JOB_KIND,
                    ),
                )
    except Exception:  # pragma: no cover - project may have been removed.
        logger.exception("Could not mark import job %s as failed", job_id)


def _mark_cancelled(
    project_dir: Path, job_id: str, imported_pages: int | None = None
) -> None:
    try:
        with project_db(project_dir) as conn:
            now = _now()
            if imported_pages is None:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'cancelled', current_file = NULL, completed_at = ?,
                        updated_at = ?
                    WHERE id = ? AND kind = ?
                    """,
                    (now, now, job_id, JOB_KIND),
                )
            else:
                row = conn.execute(
                    "SELECT total_pages FROM jobs WHERE id = ? AND kind = ?",
                    (job_id, JOB_KIND),
                ).fetchone()
                total = int(row["total_pages"] or 0) if row is not None else 0
                progress = min(1.0, imported_pages / total) if total else 0.0
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'cancelled', current_file = NULL, completed_at = ?,
                        imported_pages = ?, progress = ?, updated_at = ?
                    WHERE id = ? AND kind = ?
                    """,
                    (now, imported_pages, progress, now, job_id, JOB_KIND),
                )
    except Exception:  # pragma: no cover - project may have been removed.
        logger.exception("Could not mark import job %s as cancelled", job_id)


def _update_running(project_dir: Path, job_id: str) -> None:
    with project_db(project_dir) as conn:
        conn.execute(
            """
            UPDATE jobs SET status = 'running', updated_at = ?
            WHERE id = ? AND kind = ? AND status IN ('queued', 'cancelling')
            """,
            (_now(), job_id, JOB_KIND),
        )


def _update_progress(
    project_dir: Path, job_id: str, progress: page_service.ImportProgress
) -> None:
    fraction = (
        min(1.0, progress.imported_pages / progress.total_pages)
        if progress.total_pages
        else 0.0
    )
    try:
        with project_db(project_dir) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET progress = ?, imported_pages = ?, current_file = ?, updated_at = ?
                WHERE id = ? AND kind = ? AND status IN ('queued', 'running', 'cancelling')
                """,
                (
                    fraction,
                    progress.imported_pages,
                    progress.current_file,
                    _now(),
                    job_id,
                    JOB_KIND,
                ),
            )
    except Exception:  # pragma: no cover - progress loss must not stop an import.
        logger.exception("Could not update progress for import job %s", job_id)


def _mark_succeeded(project_dir: Path, job_id: str, imported_pages: int) -> None:
    try:
        with project_db(project_dir) as conn:
            now = _now()
            conn.execute(
                """
                UPDATE jobs
                SET status = 'succeeded', progress = 1.0, imported_pages = ?,
                    current_file = NULL, error = NULL, error_code = NULL,
                    completed_at = ?, updated_at = ?
                WHERE id = ? AND kind = ?
                """,
                (imported_pages, now, now, job_id, JOB_KIND),
            )
    except Exception:  # pragma: no cover - project may have been removed.
        logger.exception("Could not mark import job %s as complete", job_id)


def create_import_job(
    project_dir: Path,
    uploads: list[tuple[str, Path]],
    inspected: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create an import job and hand the validated temporary files to a worker."""
    job_id = str(uuid.uuid4())
    total_pages = sum(int(item.get("page_count", 1)) for item in inspected)
    payload = {
        "file_count": len(inspected),
        "filenames": [item["filename"] for item in inspected],
    }
    event = threading.Event()
    active = _ActiveJob(event=event, project_dir=project_dir)

    with _registry_lock:
        _registry[job_id] = active

    try:
        with project_db(project_dir) as conn:
            now = _now()
            conn.execute(
                """
                INSERT INTO jobs (id, kind, status, progress, payload, error,
                                  created_at, updated_at, total_pages, imported_pages)
                VALUES (?, ?, 'queued', 0, ?, NULL, ?, ?, ?, 0)
                """,
                (job_id, JOB_KIND, json.dumps(payload, ensure_ascii=False), now, now, total_pages),
            )
    except Exception:
        with _registry_lock:
            _registry.pop(job_id, None)
        page_service.discard_temporary_uploads(uploads)
        raise

    try:
        _get_executor().submit(_execute_import_job, job_id, project_dir, uploads, inspected)
    except RuntimeError:
        with _registry_lock:
            _registry.pop(job_id, None)
        _mark_failed(
            project_dir,
            job_id,
            "The local import worker is not available.",
            "import_worker_unavailable",
        )
        page_service.discard_temporary_uploads(uploads)

    return get_import_job(project_dir, job_id)


def get_import_job(project_dir: Path, job_id: str) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        row = _get_row(conn, job_id)
    _recover_if_stale(project_dir, row)
    with project_db(project_dir) as conn:
        row = _get_row(conn, job_id)
    return _job_payload(row)


def list_import_jobs(project_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 50))
    with project_db(project_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
            (JOB_KIND, safe_limit),
        ).fetchall()
    for row in rows:
        _recover_if_stale(project_dir, row)
    with project_db(project_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
            (JOB_KIND, safe_limit),
        ).fetchall()
    return [_job_payload(row) for row in rows]


def cancel_import_job(project_dir: Path, job_id: str) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        row = _get_row(conn, job_id)
        if row["status"] in TERMINAL_STATUSES:
            raise AppError(
                409,
                "import_not_running",
                "This import has already finished and cannot be cancelled.",
            )
        if row["status"] in ACTIVE_STATUSES:
            conn.execute(
                "UPDATE jobs SET status = 'cancelling', updated_at = ? WHERE id = ?",
                (_now(), job_id),
            )

    with _registry_lock:
        active = _registry.get(job_id)
    if active is None:
        # No live worker exists (for example after a restart): finish the job
        # immediately instead of leaving it stuck in "cancelling".
        _mark_cancelled(project_dir, job_id)
    else:
        active.event.set()

    return get_import_job(project_dir, job_id)


def _execute_import_job(
    job_id: str,
    project_dir: Path,
    uploads: list[tuple[str, Path]],
    inspected: list[dict[str, Any]],
) -> None:
    with _registry_lock:
        active = _registry.get(job_id)
    event = active.event if active is not None else None

    try:
        _update_running(project_dir, job_id)
        rows = page_service.import_uploads(
            project_dir,
            uploads,
            inspected=inspected,
            cancel=event,
            on_progress=lambda progress: _update_progress(project_dir, job_id, progress),
            keep_completed_on_failure=True,
        )
        _mark_succeeded(project_dir, job_id, len(rows))
    except page_service.ImportCancelled as exc:
        _mark_cancelled(project_dir, job_id, getattr(exc, "imported_pages", None))
    except AppError as exc:
        _mark_failed(
            project_dir,
            job_id,
            exc.message,
            exc.code,
            getattr(exc, "imported_pages", None),
        )
    except Exception as exc:
        logger.exception("Import job %s failed", job_id)
        _mark_failed(
            project_dir,
            job_id,
            "The import could not be completed.",
            "import_failed",
            getattr(exc, "imported_pages", None),
        )
    finally:
        with _registry_lock:
            _registry.pop(job_id, None)
