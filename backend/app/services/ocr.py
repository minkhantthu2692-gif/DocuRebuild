from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import resolve_within
from app.db.project_schema import project_db, utc_iso

logger = logging.getLogger(__name__)

ENGINE_NAME = "tesseract"
PREFERRED_LANGUAGES = ("eng", "mya")
CACHE_TTL_SECONDS = 15.0

_engine_cache: tuple[float, dict[str, Any]] | None = None
_engine_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _now() -> str:
    return utc_iso()


def _command_tokens(raw: str) -> list[str]:
    """Split the configured command without losing quoted Windows paths."""
    raw = (raw or "").strip()
    if not raw:
        return []
    tokens = shlex.split(raw, posix=os.name != "nt")
    cleaned: list[str] = []
    for token in tokens:
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
            token = token[1:-1]
        if token:
            cleaned.append(token)
    return cleaned


def _run_command(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    settings = get_settings()
    env = os.environ.copy()
    if settings.tessdata_dir is not None:
        env["TESSDATA_PREFIX"] = str(settings.tessdata_dir)
    # Keep Tesseract from saturating every CPU core while the local API is
    # serving the workspace. The job pool already bounds concurrency.
    env.setdefault("OMP_THREAD_LIMIT", "1")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        creationflags=creationflags,
        check=False,
    )


def _parse_version(text: str) -> str | None:
    match = re.search(r"tesseract\s+v?([0-9][0-9A-Za-z.\-]*)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _setup_hint(reason: str) -> str:
    if reason == "not_configured":
        return (
            "Set DOCUREBUILD_TESSERACT_CMD to your Tesseract executable, or install "
            "Tesseract and add it to PATH."
        )
    if reason == "not_found":
        return (
            "Tesseract was not found. Install it locally, or set "
            "DOCUREBUILD_TESSERACT_CMD to the executable."
        )
    if reason == "not_executable":
        return "The configured Tesseract command could not be run. Check the path and permissions."
    if reason == "no_languages":
        return (
            "Tesseract is installed but no language data was found. Add the eng "
            "and mya traineddata files to its tessdata folder."
        )
    return "Tesseract could not be checked. Review the local installation."


def _store_engine_status(status: dict[str, Any]) -> dict[str, Any]:
    global _engine_cache
    with _engine_lock:
        _engine_cache = (time.monotonic(), status)
    return status


def clear_engine_cache() -> None:
    global _engine_cache
    with _engine_lock:
        _engine_cache = None


def detect_engine(force: bool = False) -> dict[str, Any]:
    """Inspect the local Tesseract installation without contacting the network."""
    global _engine_cache
    with _engine_lock:
        if not force and _engine_cache is not None:
            age = time.monotonic() - _engine_cache[0]
            if age < CACHE_TTL_SECONDS:
                return dict(_engine_cache[1])

    settings = get_settings()
    tokens = _command_tokens(settings.tesseract_cmd)
    base: dict[str, Any] = {
        "engine": ENGINE_NAME,
        "available": False,
        "version": None,
        "command": settings.tesseract_cmd,
        "tessdata_dir": str(settings.tessdata_dir) if settings.tessdata_dir else None,
        "languages": [],
        "preferred_languages": [],
        "reason": None,
        "setup_hint": None,
    }

    if not tokens:
        base.update(reason="not_configured", setup_hint=_setup_hint("not_configured"))
        return _store_engine_status(base)

    try:
        version_result = _run_command([*tokens, "--version"], timeout=10)
    except FileNotFoundError:
        base.update(reason="not_found", setup_hint=_setup_hint("not_found"))
        return _store_engine_status(base)
    except PermissionError:
        base.update(reason="not_executable", setup_hint=_setup_hint("not_executable"))
        return _store_engine_status(base)
    except subprocess.TimeoutExpired:
        base.update(reason="error", setup_hint=_setup_hint("error"))
        return _store_engine_status(base)
    except OSError:
        base.update(reason="not_found", setup_hint=_setup_hint("not_found"))
        return _store_engine_status(base)

    version_text = f"{version_result.stdout}\n{version_result.stderr}".strip()
    if version_result.returncode != 0:
        base.update(reason="not_executable", setup_hint=_setup_hint("not_executable"))
        return _store_engine_status(base)

    version = _parse_version(version_text)

    try:
        languages_result = _run_command([*tokens, "--list-langs"], timeout=10)
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
        languages_result = None

    languages: list[str] = []
    if languages_result is not None:
        output = f"{languages_result.stdout}\n{languages_result.stderr}"
        for line in output.splitlines():
            candidate = line.strip()
            if not candidate or candidate.lower().startswith("list of available languages"):
                continue
            if re.fullmatch(r"[A-Za-z0-9_.\-]+", candidate):
                languages.append(candidate)

    languages = sorted(set(languages))
    if not languages:
        base.update(
            version=version,
            reason="no_languages",
            setup_hint=_setup_hint("no_languages"),
        )
        return _store_engine_status(base)

    preferred = [code for code in PREFERRED_LANGUAGES if code in languages]
    base.update(
        available=True,
        version=version,
        languages=languages,
        preferred_languages=preferred,
    )
    return _store_engine_status(base)


def engine_available() -> bool:
    return bool(detect_engine().get("available"))


def _normalise_languages(requested: list[str]) -> list[str]:
    languages: list[str] = []
    for value in requested:
        for part in str(value).split("+"):
            code = part.strip().lower()
            if code and code not in languages:
                languages.append(code)
    return languages[:4]


def _get_page(conn, page_id: str):
    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if row is None:
        raise AppError(404, "page_not_found", "Page not found.")
    return row


def _source_asset(conn, project_dir: Path, page) -> tuple[str, Path]:
    asset_id = page["display_asset_id"] or page["original_asset_id"]
    if not asset_id:
        raise AppError(409, "ocr_page_has_no_source", "This page has no source image.")
    asset = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if asset is None:
        raise AppError(404, "asset_not_found", "The page image could not be found.")
    try:
        path = resolve_within(project_dir, asset["relative_path"])
    except ValueError as exc:
        raise AppError(500, "asset_path_invalid", "Asset path is invalid.") from exc
    if not path.exists():
        raise AppError(404, "asset_file_missing", "The page image is missing from the project.")
    return asset_id, path


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            settings = get_settings()
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.ocr_max_workers),
                thread_name_prefix="docurebuild-ocr",
            )
        return _executor


def shutdown_ocr_executor() -> None:
    global _executor
    with _executor_lock:
        executor = _executor
        _executor = None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)


def start_ocr(project_dir: Path, page_id: str, languages: list[str]) -> dict[str, Any]:
    status = detect_engine()
    if not status.get("available"):
        raise AppError(
            409,
            "ocr_unavailable",
            status.get("setup_hint") or "A local OCR engine is not available.",
        )

    requested = _normalise_languages(languages)
    if not requested:
        requested = [code for code in PREFERRED_LANGUAGES if code in status["languages"]][:1]
    if not requested:
        raise AppError(409, "ocr_language_unavailable", "No OCR language is available.")

    missing = [code for code in requested if code not in status["languages"]]
    if missing:
        raise AppError(
            409,
            "ocr_language_unavailable",
            f"OCR language data is not installed: {', '.join(missing)}.",
        )

    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        source_asset_id, _ = _source_asset(conn, project_dir, page)
        run_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            """
            INSERT INTO ocr_runs (id, page_id, status, engine, engine_version, languages,
                                  source_asset_id, rotation, text, created_at, updated_at)
            VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, '', ?, ?)
            """,
            (
                run_id,
                page_id,
                ENGINE_NAME,
                status.get("version"),
                "+".join(requested),
                source_asset_id,
                int(page["rotation"]),
                now,
                now,
            ),
        )

    try:
        _get_executor().submit(_execute_ocr_run, run_id, project_dir, page_id, requested)
    except RuntimeError:
        _mark_failed(
            project_dir,
            run_id,
            "The OCR worker is not available.",
            "ocr_worker_unavailable",
        )

    return get_run(project_dir, run_id)


def _mark_failed(project_dir: Path, run_id: str, message: str, code: str) -> None:
    try:
        with project_db(project_dir) as conn:
            now = _now()
            conn.execute(
                """
                UPDATE ocr_runs
                SET status = 'failed', error = ?, error_code = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (message, code, now, now, run_id),
            )
    except Exception:  # pragma: no cover - project may have been removed.
        logger.exception("Could not mark OCR run %s as failed", run_id)


def _execute_ocr_run(
    run_id: str, project_dir: Path, page_id: str, languages: list[str]
) -> None:
    try:
        with project_db(project_dir) as conn:
            conn.execute(
                "UPDATE ocr_runs SET status = 'running', updated_at = ? WHERE id = ?",
                (_now(), run_id),
            )
        result = _perform_ocr(project_dir, page_id, languages)
        with project_db(project_dir) as conn:
            conn.execute("DELETE FROM ocr_blocks WHERE run_id = ?", (run_id,))
            now = _now()
            for block in result["blocks"]:
                conn.execute(
                    """
                    INSERT INTO ocr_blocks (id, run_id, page_id, block_index, kind, text,
                                            confidence, x, y, width, height, line_count,
                                            word_count, verified, corrected, created_at,
                                            updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        run_id,
                        page_id,
                        block["block_index"],
                        block["kind"],
                        block["text"],
                        block["confidence"],
                        block["x"],
                        block["y"],
                        block["width"],
                        block["height"],
                        block["line_count"],
                        block["word_count"],
                        now,
                        now,
                    ),
                )
            conn.execute(
                """
                UPDATE ocr_runs
                SET status = 'succeeded', text = ?, mean_confidence = ?, engine_version = ?,
                    error = NULL, error_code = NULL, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    result["text"],
                    result["mean_confidence"],
                    result["engine_version"],
                    now,
                    now,
                    run_id,
                ),
            )
    except AppError as exc:
        _mark_failed(project_dir, run_id, exc.message, exc.code)
    except subprocess.TimeoutExpired:
        _mark_failed(
            project_dir,
            run_id,
            "OCR timed out. Try a smaller page or raise DOCUREBUILD_OCR_TIMEOUT_SECONDS.",
            "ocr_timeout",
        )
    except Exception:
        logger.exception("OCR run %s failed", run_id)
        _mark_failed(
            project_dir,
            run_id,
            "OCR failed. Check the local engine installation and try again.",
            "ocr_failed",
        )


def _prepare_image(path: Path) -> tuple[Path, float]:
    settings = get_settings()
    try:
        with Image.open(path) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise AppError(422, "ocr_image_unreadable", "The page image could not be read.") from exc

    scale = 1.0
    max_edge = max(1, settings.ocr_max_image_edge)
    if max(image.size) > max_edge:
        scale = max_edge / float(max(image.size))
        new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=str(settings.tmp_dir), suffix=".png")
    os.close(handle)
    temp_path = Path(name)
    try:
        image.save(temp_path, format="PNG", optimize=False)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise AppError(500, "ocr_image_unreadable", "The page image could not be prepared.") from exc
    finally:
        image.close()
    return temp_path, scale


def _scale(value: float, scale: float) -> int:
    return int(round(value / scale)) if scale > 0 else int(round(value))


def _classify_block(
    text: str, max_line_height: float, median_line_height: float, word_count: int
) -> str:
    stripped = text.strip()
    if re.match(r"^(?:\d+[.)]|[•●▪◦·*\-–—])\s+", stripped):
        return "list_item"
    first_line = stripped.splitlines()[0].strip() if stripped else ""
    if (
        max_line_height >= max(1.0, median_line_height * 1.35)
        and word_count <= 14
        and first_line
        and not re.search(r"[.!?;:,]$", first_line)
    ):
        return "heading"
    if first_line and first_line.isupper() and len(first_line) <= 80 and word_count <= 12:
        return "heading"
    return "paragraph"


def _parse_tsv(tsv: str, scale: float) -> tuple[str, list[dict[str, Any]], float | None]:
    words: list[dict[str, Any]] = []
    for raw_line in tsv.splitlines():
        if not raw_line.strip() or raw_line.startswith("level\t"):
            continue
        parts = raw_line.split("\t")
        if len(parts) < 12:
            continue
        try:
            level = int(parts[0])
        except ValueError:
            continue
        if level != 5:
            continue
        text = "\t".join(parts[11:]).strip()
        if not text:
            continue
        try:
            confidence = float(parts[10])
        except ValueError:
            confidence = -1.0
        if confidence < 0:
            confidence = None
        try:
            left, top, width, height = (int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9]))
        except ValueError:
            continue
        words.append(
            {
                "block": int(parts[2]),
                "paragraph": int(parts[3]),
                "line": int(parts[4]),
                "word": int(parts[5]),
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "confidence": confidence,
                "text": text,
            }
        )

    if not words:
        return "", [], None

    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for word in words:
        grouped.setdefault((word["block"], word["paragraph"]), []).append(word)

    line_heights: list[float] = []
    prepared: list[dict[str, Any]] = []
    for (block_number, paragraph_number), block_words in grouped.items():
        block_words.sort(key=lambda item: (item["line"], item["word"]))
        lines: dict[int, list[dict[str, Any]]] = {}
        for word in block_words:
            lines.setdefault(word["line"], []).append(word)

        line_texts: list[str] = []
        line_heights_for_block: list[float] = []
        left = top = None
        right = bottom = None
        for line_number in sorted(lines):
            line_words = lines[line_number]
            line_text = " ".join(word["text"] for word in line_words).strip()
            if not line_text:
                continue
            line_texts.append(line_text)
            line_left = min(word["left"] for word in line_words)
            line_top = min(word["top"] for word in line_words)
            line_right = max(word["left"] + word["width"] for word in line_words)
            line_bottom = max(word["top"] + word["height"] for word in line_words)
            line_heights_for_block.append(float(line_bottom - line_top))
            line_heights.append(float(line_bottom - line_top))
            left = line_left if left is None else min(left, line_left)
            top = line_top if top is None else min(top, line_top)
            right = line_right if right is None else max(right, line_right)
            bottom = line_bottom if bottom is None else max(bottom, line_bottom)

        if not line_texts or left is None or top is None or right is None or bottom is None:
            continue

        confidences = [
            word["confidence"] for word in block_words if word["confidence"] is not None
        ]
        confidence = (
            round(sum(confidences) / len(confidences), 1) if confidences else None
        )
        prepared.append(
            {
                "block_number": block_number,
                "paragraph_number": paragraph_number,
                "text": "\n".join(line_texts),
                "confidence": confidence,
                "x": _scale(left, scale),
                "y": _scale(top, scale),
                "width": _scale(right - left, scale),
                "height": _scale(bottom - top, scale),
                "line_count": len(line_texts),
                "word_count": sum(len(line.split()) for line in line_texts),
                "max_line_height": max(line_heights_for_block),
            }
        )

    if not prepared:
        return "", [], None

    median_height = median(line_heights) if line_heights else 1.0
    prepared.sort(key=lambda item: (item["block_number"], item["paragraph_number"]))
    blocks: list[dict[str, Any]] = []
    for index, item in enumerate(prepared, start=1):
        blocks.append(
            {
                "block_index": index,
                "kind": _classify_block(
                    item["text"], item["max_line_height"], median_height, item["word_count"]
                ),
                "text": item["text"],
                "confidence": item["confidence"],
                "x": item["x"],
                "y": item["y"],
                "width": item["width"],
                "height": item["height"],
                "line_count": item["line_count"],
                "word_count": item["word_count"],
            }
        )

    all_confidences = [
        word["confidence"] for word in words if word["confidence"] is not None
    ]
    mean_confidence = (
        round(sum(all_confidences) / len(all_confidences), 1) if all_confidences else None
    )
    text = "\n\n".join(block["text"] for block in blocks)
    return text, blocks, mean_confidence


def _perform_ocr(
    project_dir: Path, page_id: str, languages: list[str]
) -> dict[str, Any]:
    settings = get_settings()
    status = detect_engine()
    tokens = _command_tokens(settings.tesseract_cmd)
    if not tokens:
        raise AppError(409, "ocr_unavailable", "A local OCR engine is not configured.")

    with project_db(project_dir) as conn:
        page = _get_page(conn, page_id)
        _, image_path = _source_asset(conn, project_dir, page)

    temp_path, scale = _prepare_image(image_path)
    try:
        result = _run_command(
            [
                *tokens,
                str(temp_path),
                "stdout",
                "-l",
                "+".join(languages),
                "--psm",
                "3",
                "-c",
                "tessedit_create_tsv=1",
            ],
            timeout=max(10, settings.ocr_timeout_seconds),
        )
    finally:
        temp_path.unlink(missing_ok=True)

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        message = detail[-1] if detail else "Tesseract could not process this page."
        raise AppError(422, "ocr_failed", message[:500])

    if not result.stdout.lstrip().startswith("level\t"):
        raise AppError(
            422,
            "ocr_failed",
            "Tesseract did not return structured text. Check the tessdata configuration.",
        )

    text, blocks, mean_confidence = _parse_tsv(result.stdout, scale)
    return {
        "engine_version": status.get("version"),
        "text": text,
        "blocks": blocks,
        "mean_confidence": mean_confidence,
    }


def _run_payload(conn, run) -> dict[str, Any]:
    blocks = conn.execute(
        "SELECT * FROM ocr_blocks WHERE run_id = ? ORDER BY block_index ASC",
        (run["id"],),
    ).fetchall()
    page = conn.execute("SELECT * FROM pages WHERE id = ?", (run["page_id"],)).fetchone()
    current_source = (
        (page["display_asset_id"] or page["original_asset_id"]) if page is not None else None
    )
    stale = bool(
        page is None
        or run["source_asset_id"] != current_source
        or int(run["rotation"]) != int(page["rotation"])
    )
    languages = [item for item in (run["languages"] or "").split("+") if item]
    return {
        "id": run["id"],
        "page_id": run["page_id"],
        "status": run["status"],
        "engine": run["engine"],
        "engine_version": run["engine_version"],
        "languages": languages,
        "source_asset_id": run["source_asset_id"],
        "rotation": int(run["rotation"]),
        "mean_confidence": run["mean_confidence"],
        "text": run["text"],
        "error": run["error"],
        "error_code": run["error_code"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "completed_at": run["completed_at"],
        "stale": stale,
        "blocks": [
            {
                **dict(block),
                "verified": bool(block["verified"]),
                "corrected": bool(block["corrected"]),
            }
            for block in blocks
        ],
    }


def get_run(project_dir: Path, run_id: str) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        run = conn.execute("SELECT * FROM ocr_runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            raise AppError(404, "ocr_run_not_found", "OCR run not found.")
        return _run_payload(conn, run)


def get_latest_ocr(project_dir: Path, page_id: str) -> dict[str, Any] | None:
    with project_db(project_dir) as conn:
        _get_page(conn, page_id)
        run = conn.execute(
            "SELECT * FROM ocr_runs WHERE page_id = ? ORDER BY created_at DESC LIMIT 1",
            (page_id,),
        ).fetchone()
        return _run_payload(conn, run) if run is not None else None


def _refresh_run_text(conn, run_id: str) -> None:
    rows = conn.execute(
        "SELECT text FROM ocr_blocks WHERE run_id = ? ORDER BY block_index ASC",
        (run_id,),
    ).fetchall()
    text = "\n\n".join(row["text"] for row in rows if row["text"].strip())
    conn.execute(
        "UPDATE ocr_runs SET text = ?, updated_at = ? WHERE id = ?",
        (text, _now(), run_id),
    )


def update_block(
    project_dir: Path,
    page_id: str,
    block_id: str,
    *,
    text: str | None = None,
    verified: bool | None = None,
) -> dict[str, Any]:
    with project_db(project_dir) as conn:
        block = conn.execute(
            "SELECT * FROM ocr_blocks WHERE id = ? AND page_id = ?",
            (block_id, page_id),
        ).fetchone()
        if block is None:
            raise AppError(404, "ocr_block_not_found", "OCR text block not found.")
        run = conn.execute("SELECT * FROM ocr_runs WHERE id = ?", (block["run_id"],)).fetchone()
        if run is None:
            raise AppError(404, "ocr_run_not_found", "OCR run not found.")
        if run["status"] != "succeeded":
            raise AppError(409, "ocr_not_ready", "OCR has not finished for this page.")

        new_text = block["text"] if text is None else text
        corrected = 1 if new_text != block["text"] else int(block["corrected"])
        if verified is not None:
            new_verified = 1 if verified else 0
        elif new_text != block["text"]:
            # A manual correction starts unverified until the user confirms it.
            new_verified = 0
        else:
            new_verified = int(block["verified"])

        conn.execute(
            """
            UPDATE ocr_blocks
            SET text = ?, verified = ?, corrected = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_text, new_verified, corrected, _now(), block_id),
        )
        _refresh_run_text(conn, run["id"])
        updated_run = conn.execute(
            "SELECT * FROM ocr_runs WHERE id = ?", (run["id"],)
        ).fetchone()
        return _run_payload(conn, updated_run)
