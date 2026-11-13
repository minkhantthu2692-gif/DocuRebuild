"""Create due automatic backup copies from an external scheduler.

The application creates an automatic copy after a project is opened. This module
adds an optional, explicitly scheduled entry point for when the app is closed, so
a user can run it from Windows Task Scheduler, cron or a systemd timer.

It is not a daemon: it starts, reads the saved backup preferences, creates at most
one copy per due project, prints a short summary and exits. It only reads and
writes local application data; nothing is uploaded, and it never contacts a
provider. Automatic copies must be enabled in Settings, and the same interval and
retention limits apply.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from app.db.models import Project
from app.db.session import get_session_factory, run_migrations
from app.services import local_backups
from app.services.settings import get_app_settings

logger = logging.getLogger(__name__)


def run_due_backups() -> dict[str, object]:
    """Create one copy per project whose newest copy is old enough.

    Returns a summary with ``enabled``, ``created`` and ``failed`` counts. A
    failure for one project is logged and does not stop the others, so one broken
    project cannot block every later backup.
    """
    session = get_session_factory()()
    created = 0
    failed = 0
    try:
        preferences = get_app_settings(session).backups
        if not preferences.auto_on_open:
            return {"enabled": False, "created": 0, "failed": 0}

        projects = session.scalars(select(Project).order_by(Project.name)).all()
        for project in projects:
            try:
                copy = local_backups.auto_copy(
                    project,
                    preferences.interval_hours,
                    preferences.keep_copies,
                )
            except Exception:
                failed += 1
                logger.warning(
                    "Scheduled backup failed for project %s", project.id, exc_info=True
                )
                continue
            if copy is not None:
                created += 1
                logger.info(
                    "Created scheduled backup copy %s for project %s",
                    copy["filename"],
                    project.name,
                )
        return {"enabled": True, "created": created, "failed": failed}
    finally:
        session.close()


def main() -> int:
    """Run one scheduled pass and return a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # The app may never have started on this data directory, so make sure the
    # database schema exists before reading projects or settings.
    run_migrations()
    result = run_due_backups()
    if not result["enabled"]:
        print("Automatic backups are disabled in Settings; no copies were created.")
    else:
        print(
            f"Created {result['created']} backup copy(ies); "
            f"{result['failed']} failed."
        )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
