"""Large-document performance and cancellation drill for the desktop sidecar.

Runs the packaged ``docurebuild-backend.exe`` against a disposable data folder,
imports progressively larger raster PDFs, OCRs sample pages, measures document
save/read/export latency, repeats cancellations and simulates a crash mid-import.

Everything is measured from outside the process through the same HTTP API the
Electron shell uses, so the numbers describe the shipped sidecar rather than a
development server. Memory is read from the Windows process counters.

Example (from the repository root, with the installed app present):

    backend/.venv/Scripts/python.exe scripts/performance-drill.py \
        --out docs/performance/sidecar-drill.json

Pass ``--keep`` to keep the disposable data folder for inspection.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import winreg
from collections.abc import Iterable
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Process and machine information
# ---------------------------------------------------------------------------

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
psapi.GetProcessMemoryInfo.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
    wintypes.DWORD,
]
psapi.GetProcessMemoryInfo.restype = wintypes.BOOL


def _process_snapshot() -> dict[int, tuple[str, int]]:
    """Return ``pid -> (image name, parent pid)`` for the whole machine."""
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1:
        return {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    result: dict[int, tuple[str, int]] = {}
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            result[int(entry.th32ProcessID)] = (
                entry.szExeFile,
                int(entry.th32ParentProcessID),
            )
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return result


def _descendant_pids(root_pid: int) -> list[int]:
    snapshot = _process_snapshot()
    found: list[int] = []
    frontier = [root_pid]
    while frontier:
        parent = frontier.pop()
        for pid, (_name, parent_pid) in snapshot.items():
            if parent_pid == parent and pid not in found:
                found.append(pid)
                frontier.append(pid)
    return found


def working_set(pid: int) -> int | None:
    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    finally:
        kernel32.CloseHandle(handle)


def orphan_names(sidecar_pid: int | None) -> dict[str, int]:
    """Count live ``tesseract`` and sidecar processes not owned by our root."""
    snapshot = _process_snapshot()
    owned: set[int] = set()
    if sidecar_pid is not None:
        owned = {sidecar_pid, *_descendant_pids(sidecar_pid)}
    counts: dict[str, int] = {}
    for pid, (name, _parent) in snapshot.items():
        lowered = name.lower()
        if lowered in {"tesseract.exe", "docurebuild-backend.exe"} and pid not in owned:
            counts[lowered] = counts.get(lowered, 0) + 1
    return counts


class MemorySampler:
    """Poll one process working set in the background."""

    def __init__(self, pid: int, interval: float = 0.1) -> None:
        self.pid = pid
        self.interval = interval
        self.samples: list[int] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            value = working_set(self.pid)
            if value is not None:
                self.samples.append(value)
            self._stop.wait(self.interval)

    def __enter__(self) -> MemorySampler:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    @property
    def peak(self) -> int | None:
        return max(self.samples) if self.samples else None

    @property
    def start(self) -> int | None:
        return self.samples[0] if self.samples else None

    @property
    def end(self) -> int | None:
        return self.samples[-1] if self.samples else None


def _cpu_name() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except OSError:
        return platform.processor() or "unknown"


def _total_ram() -> int | None:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return int(status.ullTotalPhys)
    return None


def machine_info() -> dict[str, Any]:
    ram = _total_ram()
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu": _cpu_name(),
        "logical_cores": os.cpu_count(),
        "ram_gb": round(ram / 1024**3, 1) if ram else None,
        "python": platform.python_version(),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PAGE_WIDTH, PAGE_HEIGHT = 1240, 1755  # 150 DPI US Letter
PARAGRAPHS = [
    "The reconstruction workspace keeps every imported page as an immutable source. "
    "Processing writes a separate display image, so the original scan is never changed.",
    "Text extraction produces reviewable blocks with confidence and geometry. Nothing is "
    "inserted into the document until the reviewer confirms it.",
    "Tables and figures are reconstructed from the geometry that the extraction engine "
    "reports. Ambiguous cells stay unverified instead of being invented.",
    "Exports are generated locally. Markdown, plain text, Word processing and PDF output "
    "share the same reviewed document content.",
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arial.ttf", "calibri.ttf", "segoeui.ttf"):
        path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _page_image(index: int) -> Image.Image:
    image = Image.new("L", (PAGE_WIDTH, PAGE_HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    title = _font(42)
    body = _font(26)
    draw.text((90, 80), f"Scanned reference page {index + 1}", fill=20, font=title)
    y = 170
    for offset in range(18):
        paragraph = PARAGRAPHS[(index + offset) % len(PARAGRAPHS)]
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if draw.textlength(candidate, font=body) > PAGE_WIDTH - 200:
                draw.text((90, y), line, fill=30, font=body)
                y += 38
                line = word
            else:
                line = candidate
        if line:
            draw.text((90, y), line, fill=30, font=body)
            y += 58
        if y > PAGE_HEIGHT - 160:
            break
    draw.text(
        (90, PAGE_HEIGHT - 90),
        f"Page {index + 1} - disposable performance fixture",
        fill=90,
        font=body,
    )
    return image


def build_scanned_pdf(path: Path, page_count: int, *, unique_pages: int = 8) -> None:
    """Create a raster-only PDF so importing and OCR exercise the real paths."""
    import fitz

    images: list[bytes] = []
    for index in range(min(unique_pages, page_count)):
        image = _page_image(index)
        buffer = tempfile.SpooledTemporaryFile()
        image.save(buffer, format="JPEG", quality=80, optimize=True)
        buffer.seek(0)
        images.append(buffer.read())
        buffer.close()
        image.close()

    doc = fitz.open()
    rect = fitz.Rect(0, 0, 612, 792)
    for index in range(page_count):
        page = doc.new_page(width=612, height=792)
        page.insert_image(rect, stream=images[index % len(images)], keep_proportion=False)
    doc.save(str(path), deflate=True, garbage=4)
    doc.close()


def tree_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def count_files(path: Path, suffix: str) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob(f"*{suffix}") if item.is_file())


# ---------------------------------------------------------------------------
# API client and job helpers
# ---------------------------------------------------------------------------


class Api:
    def __init__(self, port: int, token: str) -> None:
        self.client = httpx.Client(
            base_url=f"http://127.0.0.1:{port}/api",
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(300.0, connect=10.0),
        )

    def close(self) -> None:
        self.client.close()

    def create_project(self, name: str) -> dict[str, Any]:
        response = self.client.post("/projects", json={"name": name, "description": ""})
        response.raise_for_status()
        return response.json()

    def import_pdf(self, project_id: str, path: Path) -> dict[str, Any]:
        with path.open("rb") as handle:
            response = self.client.post(
                f"/projects/{project_id}/imports",
                files={"files": (path.name, handle, "application/pdf")},
            )
        response.raise_for_status()
        return response.json()

    def job(self, project_id: str, job_id: str) -> dict[str, Any]:
        response = self.client.get(f"/projects/{project_id}/imports/{job_id}")
        response.raise_for_status()
        return response.json()

    def jobs(self, project_id: str) -> list[dict[str, Any]]:
        response = self.client.get(f"/projects/{project_id}/imports")
        response.raise_for_status()
        return response.json()

    def cancel(self, project_id: str, job_id: str) -> dict[str, Any]:
        response = self.client.post(f"/projects/{project_id}/imports/{job_id}/cancel")
        response.raise_for_status()
        return response.json()

    def pages(self, project_id: str) -> list[dict[str, Any]]:
        response = self.client.get(f"/projects/{project_id}/pages")
        response.raise_for_status()
        return response.json()

    def asset(self, project_id: str, asset_id: str) -> tuple[bytes, float]:
        started = time.perf_counter()
        response = self.client.get(f"/projects/{project_id}/assets/{asset_id}/file")
        response.raise_for_status()
        return response.content, time.perf_counter() - started

    def start_ocr(self, project_id: str, page_id: str, mode: int = 3) -> dict[str, Any]:
        response = self.client.post(
            f"/projects/{project_id}/pages/{page_id}/ocr",
            json={"languages": ["eng"], "page_segmentation_mode": mode},
        )
        response.raise_for_status()
        return response.json()

    def ocr_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        response = self.client.get(f"/projects/{project_id}/ocr/runs/{run_id}")
        response.raise_for_status()
        return response.json()

    def write_document(
        self, project_id: str, content: dict[str, Any], plain_text: str
    ) -> dict[str, Any]:
        response = self.client.put(
            f"/projects/{project_id}/document",
            json={"content": content, "plain_text": plain_text},
        )
        response.raise_for_status()
        return response.json()

    def document(self, project_id: str) -> dict[str, Any]:
        response = self.client.get(f"/projects/{project_id}/document")
        response.raise_for_status()
        return response.json()

    def export(self, project_id: str, fmt: str) -> tuple[int, float]:
        started = time.perf_counter()
        response = self.client.get(
            f"/projects/{project_id}/document/export", params={"format": fmt}
        )
        response.raise_for_status()
        return len(response.content), time.perf_counter() - started


def wait_for_terminal(
    api: Api, project_id: str, job_id: str, *, timeout: float = 900
) -> tuple[dict[str, Any], list[int]]:
    deadline = time.perf_counter() + timeout
    samples: list[int] = []
    while time.perf_counter() < deadline:
        job = api.job(project_id, job_id)
        samples.append(int(job["imported_pages"]))
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job, samples
        time.sleep(0.1)
    raise TimeoutError(f"Import job {job_id} did not finish within {timeout}s")


def wait_for_ocr(api: Api, project_id: str, run_id: str, *, timeout: float = 300) -> dict[str, Any]:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        run = api.ocr_run(project_id, run_id)
        if run["status"] in {"succeeded", "failed", "cancelled"}:
            return run
        time.sleep(0.1)
    raise TimeoutError(f"OCR run {run_id} did not finish within {timeout}s")


def tiptap_document(paragraphs: int, words_per_paragraph: int = 50) -> tuple[dict[str, Any], str]:
    content: list[dict[str, Any]] = []
    texts: list[str] = []
    word = "reconstruction"
    for index in range(paragraphs):
        sentence = " ".join(
            f"{word}{((index + offset) % 97)}" for offset in range(words_per_paragraph)
        )
        texts.append(sentence)
        content.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": sentence}],
            }
        )
    return {"type": "doc", "content": content}, "\n\n".join(texts)


# ---------------------------------------------------------------------------
# Drill
# ---------------------------------------------------------------------------


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_live_sidecars: list[Sidecar] = []


class Sidecar:
    def __init__(self, executable: Path, data_dir: Path, log_dir: Path) -> None:
        self.executable = executable
        self.data_dir = data_dir
        self.log_dir = log_dir
        self.port = free_port()
        self.process: subprocess.Popen[bytes] | None = None
        self.startup_seconds: float | None = None
        self.token = "perf-drill-token"

    def start(self) -> None:
        self.port = free_port()
        env = {
            **os.environ,
            "DOCUREBUILD_DATA_DIR": str(self.data_dir),
            "DOCUREBUILD_API_TOKEN": self.token,
            "DOCUREBUILD_ENVIRONMENT": "production",
            "DOCUREBUILD_LOG_DIR": str(self.log_dir),
            "PYTHONUTF8": "1",
        }
        tesseract = self.executable.parent.parent / "tesseract" / "tesseract.exe"
        if tesseract.exists():
            env["DOCUREBUILD_TESSERACT_CMD"] = str(tesseract)
            env["DOCUREBUILD_TESSDATA_DIR"] = str(tesseract.parent / "tessdata")
        started = time.perf_counter()
        self.process = subprocess.Popen(  # noqa: S603 - fixed installed binary
            [str(self.executable), "--port", str(self.port)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _live_sidecars.append(self)
        deadline = time.perf_counter() + 90
        while time.perf_counter() < deadline:
            try:
                response = httpx.get(
                    f"http://127.0.0.1:{self.port}/api/health",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=1.0,
                )
                if response.status_code == 200:
                    payload = response.json()
                    if Path(payload.get("data_dir", "")).resolve() != self.data_dir.resolve():
                        raise RuntimeError(
                            "A different sidecar is already using this port: "
                            f"{payload.get('data_dir')}"
                        )
                    self.startup_seconds = time.perf_counter() - started
                    return
            except httpx.HTTPError:
                pass
            if self.process.poll() is not None:
                raise RuntimeError(f"Sidecar exited with code {self.process.returncode}")
            time.sleep(0.1)
        raise RuntimeError("Sidecar did not become healthy")

    @property
    def pid(self) -> int:
        assert self.process is not None
        return self.process.pid

    def kill_hard(self) -> None:
        assert self.process is not None
        self.process.kill()
        self.process.wait(timeout=30)

    def stop(self) -> int | None:
        if self.process is None or self.process.poll() is not None:
            return None if self.process is None else self.process.returncode
        self.process.terminate()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=30)
        return self.process.returncode

    def health(self) -> dict[str, Any]:
        response = httpx.get(
            f"http://127.0.0.1:{self.port}/api/health",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=5.0,
        )
        response.raise_for_status()
        return response.json()


def run_drill(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="docurebuild-perf-", dir=args.temp_root)).resolve()
    data_dir = root / "data"
    fixtures = root / "fixtures"
    logs = root / "logs"
    for path in (data_dir, fixtures, logs):
        path.mkdir(parents=True, exist_ok=True)
    print(f"[drill] disposable root: {root}")

    executable = Path(args.sidecar).expanduser().resolve()
    if not executable.exists():
        raise SystemExit(f"Sidecar not found: {executable}")
    repo_root = Path(__file__).resolve().parent.parent
    try:
        sidecar_label = str(executable.relative_to(repo_root))
    except ValueError:
        sidecar_label = executable.name

    result: dict[str, Any] = {
        "machine": machine_info(),
        "sidecar": sidecar_label,
        "sidecar_version": None,
        "startup_seconds": None,
        "idle_working_set_mb": None,
        "imports": [],
        "render": [],
        "ocr": [],
        "document": [],
        "cancellation": [],
        "queue": None,
        "restart_recovery": None,
        "shutdown_during_ocr": None,
        "orphans": {},
    }

    sizes = [int(item) for item in args.sizes.split(",") if item.strip()]
    fixture_paths: dict[int, Path] = {}
    for size in sorted(
        set(sizes) | {20, args.cancel_pages, args.queue_pages, args.recovery_pages}
    ):
        path = fixtures / f"scanned-{size}.pdf"
        print(f"[fixture] building {size}-page scanned PDF")
        build_scanned_pdf(path, size)
        fixture_paths[size] = path
    result["fixtures"] = {
        str(size): {"path": path.name, "bytes": path.stat().st_size}
        for size, path in fixture_paths.items()
    }

    sidecar = Sidecar(executable, data_dir, logs)
    sidecar.start()
    result["startup_seconds"] = round(sidecar.startup_seconds or 0, 2)
    result["sidecar_version"] = sidecar.health().get("version")
    time.sleep(2)
    result["idle_working_set_mb"] = round((working_set(sidecar.pid) or 0) / 1024**2, 1)
    api = Api(sidecar.port, sidecar.token)

    # Progressively larger imports -------------------------------------------------
    projects: dict[int, dict[str, Any]] = {}
    for size in sizes:
        name = f"Perf {size} pages"
        project = api.create_project(name)
        project_dir = Path(project.get("directory") or data_dir / "projects" / project["id"])
        tmp_dir = data_dir / "tmp"
        tmp_before = count_files(tmp_dir, "")
        print(f"[import] {size} pages")
        with MemorySampler(sidecar.pid) as sampler:
            started = time.perf_counter()
            job = api.import_pdf(project["id"], fixture_paths[size])
            final, progress = wait_for_terminal(api, project["id"], job["id"])
            duration = time.perf_counter() - started
            time.sleep(1.0)
        pages = api.pages(project["id"])
        tmp_after = count_files(tmp_dir, "")
        record = {
            "pages_requested": size,
            "status": final["status"],
            "duration_seconds": round(duration, 2),
            "seconds_per_page": round(duration / size, 3),
            "imported_pages": final["imported_pages"],
            "page_rows": len(pages),
            "progress_samples": len(progress),
            "working_set_start_mb": round((sampler.start or 0) / 1024**2, 1),
            "working_set_peak_mb": round((sampler.peak or 0) / 1024**2, 1),
            "working_set_end_mb": round((sampler.end or 0) / 1024**2, 1),
            "project_storage_mb": round(tree_size(project_dir) / 1024**2, 1),
            "tmp_files_before": tmp_before,
            "tmp_files_after": tmp_after,
        }
        result["imports"].append(record)
        projects[size] = {"project": project, "pages": pages, "record": record}
        print(
            f"[import] {size} pages in {duration:.2f}s "
            f"({record['seconds_per_page']}s/page), peak {record['working_set_peak_mb']} MB"
        )

        # Source rendering / asset serving latency.
        if pages:
            render_samples = []
            for index in sorted({0, len(pages) // 2, len(pages) - 1}):
                page = pages[index]
                asset_id = page["display_asset_id"]
                if not asset_id:
                    continue
                body, seconds = api.asset(project["id"], asset_id)
                render_samples.append(
                    {
                        "page_index": index,
                        "bytes": len(body),
                        "seconds": round(seconds, 3),
                    }
                )
            result["render"].append({"pages": size, "samples": render_samples})

    # Repeated imports: memory must return to a stable level, not step up per PDF.
    stability_project = api.create_project("Perf memory stability")
    stability: list[dict[str, Any]] = []
    for repeat in range(1, args.memory_repeats + 1):
        job = api.import_pdf(stability_project["id"], fixture_paths[10])
        final, _ = wait_for_terminal(api, stability_project["id"], job["id"])
        time.sleep(0.5)
        stability.append(
            {
                "repeat": repeat,
                "status": final["status"],
                "working_set_mb": round((working_set(sidecar.pid) or 0) / 1024**2, 1),
            }
        )
    result["memory_stability"] = stability
    print(f"[memory] {args.memory_repeats} repeated imports: {[s['working_set_mb'] for s in stability]}")

    # OCR sample pages -------------------------------------------------------------
    ocr_project = projects.get(sizes[-1])
    if ocr_project:
        pages = ocr_project["pages"]
        project_id = ocr_project["project"]["id"]
        indexes = sorted({0, len(pages) // 2, len(pages) - 1}) if pages else []
        for index in indexes[: args.ocr_samples]:
            page = pages[index]
            print(f"[ocr] page index {index}")
            with MemorySampler(sidecar.pid, interval=0.05) as sampler:
                started = time.perf_counter()
                run = api.start_ocr(project_id, page["id"], args.ocr_mode)
                completed = wait_for_ocr(api, project_id, run["id"])
                duration = time.perf_counter() - started
            result["ocr"].append(
                {
                    "page_index": index,
                    "status": completed["status"],
                    "seconds": round(duration, 2),
                    "mean_confidence": completed.get("mean_confidence"),
                    "blocks": len(completed.get("blocks", [])),
                    "working_set_peak_mb": round((sampler.peak or 0) / 1024**2, 1),
                }
            )
        time.sleep(2)
        result["ocr_idle_working_set_mb"] = round((working_set(sidecar.pid) or 0) / 1024**2, 1)
        result["tmp_files_after_ocr"] = count_files(data_dir / "tmp", "")
        result["tesseract_after_ocr"] = orphan_names(sidecar.pid).get("tesseract.exe", 0)

    # Document save/read/export ----------------------------------------------------
    doc_project = projects.get(sizes[-1]) if projects else None
    if doc_project:
        project_id = doc_project["project"]["id"]
        for paragraphs in (300, 1200):
            content, plain_text = tiptap_document(paragraphs)
            started = time.perf_counter()
            api.write_document(project_id, content, plain_text)
            write_seconds = time.perf_counter() - started
            with MemorySampler(sidecar.pid) as sampler:
                started = time.perf_counter()
                stored = api.document(project_id)
                read_seconds = time.perf_counter() - started
            exports = {}
            for fmt in ("markdown", "txt", "docx", "pdf"):
                size, seconds = api.export(project_id, fmt)
                exports[fmt] = {"bytes": size, "seconds": round(seconds, 2)}
            result["document"].append(
                {
                    "paragraphs": paragraphs,
                    "characters": len(plain_text),
                    "write_seconds": round(write_seconds, 2),
                    "read_seconds": round(read_seconds, 2),
                    "read_peak_working_set_mb": round((sampler.peak or 0) / 1024**2, 1),
                    "stored_characters": len(stored.get("plain_text", "")),
                    "exports": exports,
                }
            )
            print(
                f"[document] {paragraphs} paragraphs ({len(plain_text)} chars): "
                f"write {write_seconds:.2f}s read {read_seconds:.2f}s"
            )

    # Repeated cancellation --------------------------------------------------------
    cancel_size = args.cancel_pages
    cancel_project = api.create_project("Perf cancellation")
    cancel_dir = Path(
        cancel_project.get("directory")
        or data_dir / "projects" / cancel_project["id"]
    )
    for repeat in range(1, args.cancel_repeats + 1):
        print(f"[cancel] repeat {repeat}")
        job = api.import_pdf(cancel_project["id"], fixture_paths[cancel_size])
        time.sleep(args.cancel_after)
        polled = api.job(cancel_project["id"], job["id"])
        started = time.perf_counter()
        api.cancel(cancel_project["id"], job["id"])
        final, _progress = wait_for_terminal(api, cancel_project["id"], job["id"])
        latency = time.perf_counter() - started
        time.sleep(0.5)
        pages = api.pages(cancel_project["id"])
        source_files = count_files(cancel_dir / "source", ".pdf")
        processed_files = count_files(cancel_dir / "processed", ".png")
        thumbnail_files = count_files(cancel_dir / "thumbnails", ".webp")
        record = {
            "repeat": repeat,
            "status_at_cancel": polled["status"],
            "imported_at_cancel": polled["imported_pages"],
            "final_status": final["status"],
            "final_imported_pages": final["imported_pages"],
            "cancel_to_terminal_seconds": round(latency, 2),
            "page_rows": len(pages),
            "pages_match_imported": len(pages) == final["imported_pages"],
            "processed_files": processed_files,
            "thumbnail_files": thumbnail_files,
            "source_pdfs": source_files,
            "files_match_pages": processed_files == len(pages) and thumbnail_files == len(pages),
            "tmp_files_after": count_files(data_dir / "tmp", ""),
            "tesseract_processes": orphan_names(sidecar.pid).get("tesseract.exe", 0),
        }
        result["cancellation"].append(record)
        print(f"[cancel] {record}")

    # Cancellation must leave the project usable.
    recovery_import = api.import_pdf(cancel_project["id"], fixture_paths[20])
    after, _ = wait_for_terminal(api, cancel_project["id"], recovery_import["id"])
    result["cancellation_after_import"] = {
        "status": after["status"],
        "imported_pages": after["imported_pages"],
        "total_page_rows": len(api.pages(cancel_project["id"])),
    }

    # Job queue: one cancelled, one completed worker.
    queue_project = api.create_project("Perf queue")
    first = api.import_pdf(queue_project["id"], fixture_paths[args.queue_pages])
    second = api.import_pdf(queue_project["id"], fixture_paths[args.queue_pages])
    time.sleep(args.cancel_after)
    api.cancel(queue_project["id"], first["id"])
    first_final, _ = wait_for_terminal(api, queue_project["id"], first["id"])
    second_final, _ = wait_for_terminal(api, queue_project["id"], second["id"])
    result["queue"] = {
        "cancelled_job": first_final["status"],
        "cancelled_job_error": first_final.get("error"),
        "completed_job": second_final["status"],
        "completed_job_error": second_final.get("error"),
        "completed_pages": second_final["imported_pages"],
        "page_rows": len(api.pages(queue_project["id"])),
    }

    # Simulated crash mid-import and restart recovery -------------------------------
    recovery_project = api.create_project("Perf recovery")
    recovery_dir = Path(
        recovery_project.get("directory")
        or data_dir / "projects" / recovery_project["id"]
    )
    job = api.import_pdf(recovery_project["id"], fixture_paths[args.recovery_pages])
    deadline = time.perf_counter() + 60
    observed = None
    while time.perf_counter() < deadline:
        observed = api.job(recovery_project["id"], job["id"])
        if observed["imported_pages"] >= args.recovery_after_pages:
            break
        time.sleep(0.1)
    api.close()
    sidecar.kill_hard()
    time.sleep(0.5)
    children_after_kill = orphan_names(None)
    # Restart on the same data folder with a fresh port.
    sidecar.start()
    api = Api(sidecar.port, sidecar.token)
    recovered = api.job(recovery_project["id"], job["id"])
    recovered_pages = api.pages(recovery_project["id"])
    # Importing after recovery proves the database and page numbering survived.
    post = api.import_pdf(recovery_project["id"], fixture_paths[20])
    post_final, _ = wait_for_terminal(api, recovery_project["id"], post["id"])
    result["restart_recovery"] = {
        "crash_after_imported_pages": observed["imported_pages"] if observed else None,
        "job_status_after_restart": recovered["status"],
        "error_code": recovered["error_code"],
        "imported_pages_kept": recovered["imported_pages"],
        "page_rows_kept": len(recovered_pages),
        "post_restart_import_status": post_final["status"],
        "post_restart_total_pages": len(api.pages(recovery_project["id"])),
        "processed_files": count_files(recovery_dir / "processed", ".png"),
        "thumbnail_files": count_files(recovery_dir / "thumbnails", ".webp"),
        "tmp_files_after_restart": count_files(data_dir / "tmp", ""),
        "orphan_processes_after_kill": children_after_kill,
    }

    # Shutdown during OCR ----------------------------------------------------------
    shutdown_project = projects[sizes[-1]] if projects else None
    if shutdown_project and shutdown_project["pages"]:
        page = shutdown_project["pages"][0]
        run = api.start_ocr(shutdown_project["project"]["id"], page["id"], args.ocr_mode)
        deadline = time.perf_counter() + 15
        while time.perf_counter() < deadline:
            current = api.ocr_run(shutdown_project["project"]["id"], run["id"])
            if current["status"] in {"running", "succeeded", "failed"}:
                run = current
                break
            time.sleep(0.05)
        time.sleep(0.1)
        api.close()
        sidecar.stop()
        time.sleep(3)
        result["shutdown_during_ocr"] = {
            "run_id": run["id"],
            "run_status_at_shutdown": run["status"],
            "orphan_processes": orphan_names(None),
            "tmp_files_after_shutdown": count_files(data_dir / "tmp", ""),
        }

        # Restart and inspect the interrupted run row.
        sidecar.start()
        api = Api(sidecar.port, sidecar.token)
        record = api.ocr_run(shutdown_project["project"]["id"], run["id"])
        result["shutdown_during_ocr"]["run_status_after_restart"] = record["status"]
        result["shutdown_during_ocr"]["stale"] = record.get("stale")

    # Final cleanup and orphan check ------------------------------------------------
    api.close()
    sidecar.stop()
    time.sleep(0.5)
    result["orphans"] = orphan_names(None)
    if args.keep:
        result["disposable_root"] = str(root)
        print(f"[drill] kept disposable data at {root}")
    else:
        shutil.rmtree(root, ignore_errors=True)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sidecar",
        default=str(
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs/DocuRebuild/resources/backend/docurebuild-backend.exe"
        ),
        help="Path to the packaged docurebuild-backend executable",
    )
    parser.add_argument("--out", default="docs/performance/sidecar-drill.json")
    parser.add_argument("--sizes", default="1,10,50,200")
    parser.add_argument("--cancel-pages", type=int, default=300)
    parser.add_argument("--cancel-repeats", type=int, default=3)
    parser.add_argument("--cancel-after", type=float, default=2.0)
    parser.add_argument("--queue-pages", type=int, default=50)
    parser.add_argument("--recovery-pages", type=int, default=200)
    parser.add_argument("--recovery-after-pages", type=int, default=3)
    parser.add_argument("--memory-repeats", type=int, default=10)
    parser.add_argument("--ocr-samples", type=int, default=3)
    parser.add_argument("--ocr-mode", type=int, default=3)
    parser.add_argument("--temp-root", default=tempfile.gettempdir())
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = run_drill(args)
    finally:
        for item in list(_live_sidecars):
            if item.process is not None and item.process.poll() is None:
                item.stop()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"[drill] wrote {output}")
    print(json.dumps({k: v for k, v in result.items() if k in {
        "machine", "startup_seconds", "idle_working_set_mb", "imports",
        "memory_stability", "ocr", "document", "cancellation", "queue",
        "restart_recovery", "shutdown_during_ocr", "orphans",
    }}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
