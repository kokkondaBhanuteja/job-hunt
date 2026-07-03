"""Run services — read run state, cancel, and trigger discovery."""
from __future__ import annotations

from typing import Any

from job_hunt.storage import repo
from job_hunt.worker.runner import run_all_active_profiles


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    repo.init_db()
    return repo.list_recent_runs(limit)


def get_run(run_id: int) -> dict[str, Any] | None:
    repo.init_db()
    return repo.get_run(run_id)


def request_cancel(run_id: int) -> None:
    repo.init_db()
    repo.request_run_cancel(run_id)


def run_discovery(*, headless: bool = True) -> list[dict[str, Any]]:
    """Run a discovery+scoring cycle for all active profiles (blocking)."""
    return run_all_active_profiles(headless=headless)
