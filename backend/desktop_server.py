"""Desktop sidecar entry point.

The Electron shell starts this executable as a child process, passes a random
port and a per-launch API token through the environment, then waits for
``/api/health`` to answer. It binds loopback only and never opens a public
listener.

When packaged with PyInstaller the process has no console, so stdout and stderr
are redirected to a log file before the application is imported. The shell
shows that file's location if startup fails.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"


def _redirect_output() -> None:
    """Point stdout/stderr at the desktop log before logging is configured."""
    log_dir = os.environ.get("DOCUREBUILD_LOG_DIR")
    if not log_dir:
        return
    try:
        directory = Path(log_dir).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        stream = open(  # noqa: SIM115 - live for the whole process
            directory / "backend.log",
            "a",
            encoding="utf-8",
            buffering=1,
        )
    except OSError:
        return
    sys.stdout = stream
    sys.stderr = stream


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="docurebuild-backend",
        description="Run the DocuRebuild local API for the desktop application.",
    )
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default=DEFAULT_HOST)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("the desktop backend only binds loopback")
    return args


def main(argv: list[str] | None = None) -> int:
    _redirect_output()
    args = _parse_args(argv)

    import uvicorn

    from app.main import create_app

    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
        loop="asyncio",
        http="h11",
        ws="none",
    )
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
