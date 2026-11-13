from __future__ import annotations

from fastapi.testclient import TestClient

from app.scheduled_backup import main, run_due_backups
from app.services import local_backups


def _copies(client: TestClient, project_id: str) -> list[dict]:
    response = client.get(f"/api/projects/{project_id}/backups")
    assert response.status_code == 200, response.text
    return response.json()


def test_scheduled_backup_respects_opt_out(
    client: TestClient, project: dict
) -> None:
    result = run_due_backups()

    assert result == {"enabled": False, "created": 0, "failed": 0}
    assert _copies(client, project["id"]) == []


def test_scheduled_backup_creates_one_due_copy(
    client: TestClient, project: dict
) -> None:
    saved = client.patch(
        "/api/settings",
        json={"backups": {"auto_on_open": True, "interval_hours": 24}},
    )
    assert saved.status_code == 200, saved.text

    assert run_due_backups() == {"enabled": True, "created": 1, "failed": 0}
    assert len(_copies(client, project["id"])) == 1

    # The newest copy is now too new, so a second pass does not duplicate it.
    assert run_due_backups() == {"enabled": True, "created": 0, "failed": 0}
    assert len(_copies(client, project["id"])) == 1


def test_scheduled_backup_continues_after_one_failure(
    client: TestClient, project: dict, monkeypatch
) -> None:
    second = client.post("/api/projects", json={"name": "Second project"}).json()
    saved = client.patch(
        "/api/settings", json={"backups": {"auto_on_open": True}}
    )
    assert saved.status_code == 200, saved.text
    original = local_backups.auto_copy

    def flaky(project_obj, interval_hours: int, keep: int):
        if project_obj.id == project["id"]:
            raise RuntimeError("simulated failure")
        return original(project_obj, interval_hours, keep)

    monkeypatch.setattr(local_backups, "auto_copy", flaky)
    result = run_due_backups()

    assert result == {"enabled": True, "created": 1, "failed": 1}
    # The failed project has no copy, but the other project was still backed up.
    assert _copies(client, project["id"]) == []
    assert len(_copies(client, second["id"])) == 1


def test_command_reports_the_result_through_its_exit_code(
    client: TestClient, project: dict, monkeypatch, capsys
) -> None:
    # Opted out is a normal outcome, not a failure, so the scheduler stays quiet.
    assert main() == 0
    assert "disabled" in capsys.readouterr().out

    saved = client.patch(
        "/api/settings", json={"backups": {"auto_on_open": True}}
    )
    assert saved.status_code == 200, saved.text

    def broken(*_args, **_kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(local_backups, "auto_copy", broken)
    # A project that cannot be backed up must be visible to the scheduler.
    assert main() == 1
    assert "1 failed" in capsys.readouterr().out
