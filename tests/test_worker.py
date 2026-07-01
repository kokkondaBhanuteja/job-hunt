"""Tests for slice ④: pacing, plugin registry, search profiles, run cycle, scheduler."""
from __future__ import annotations

import pytest

from job_hunt import plugins, services
from job_hunt.enums import RunStatus
from job_hunt.plugins.base import register
from job_hunt.storage import repo
from job_hunt.worker import config, pacing, runner


def test_discovery_cap_skips_cycle_when_reached(tmp_db, monkeypatch):
    monkeypatch.setattr(repo, "count_runs_today", lambda: config.DAILY_CAP)
    assert runner.run_all_active_profiles() == []  # cap reached → no discovery runs


# ---------- pacing ----------


def test_within_active_hours_normal_window():
    assert pacing.within_active_hours(10, 0, start="09:30", end="21:00")
    assert not pacing.within_active_hours(9, 0, start="09:30", end="21:00")
    assert not pacing.within_active_hours(21, 0, start="09:30", end="21:00")  # end exclusive


def test_within_active_hours_wraps_midnight():
    assert pacing.within_active_hours(23, 0, start="22:00", end="06:00")
    assert pacing.within_active_hours(2, 0, start="22:00", end="06:00")
    assert not pacing.within_active_hours(12, 0, start="22:00", end="06:00")


def test_cap_reached():
    assert pacing.cap_reached(30, 30)
    assert not pacing.cap_reached(29, 30)


# ---------- plugin registry ----------


def test_naukri_source_is_registered():
    assert "naukri" in plugins.available_sources()
    assert plugins.get_source("naukri").name == "naukri"


def test_unknown_source_raises():
    with pytest.raises(KeyError):
        plugins.get_source("does-not-exist")


# ---------- search profiles ----------


def test_search_profile_crud(tmp_db):
    pid = services.add_profile(name="java-blr", keywords="java spring", location="bangalore", pages=2)
    rows = services.list_profiles()
    assert len(rows) == 1
    assert rows[0]["name"] == "java-blr" and rows[0]["pages"] == 2
    assert len(repo.list_active_search_profiles()) == 1

    services.set_enabled(pid, False)
    assert repo.list_active_search_profiles() == []


# ---------- run cycle (fake source — no browser) ----------


class _FakeSource:
    name = "fake"

    def discover(self, *, keyword, location, pages=1, headless=True, dry_run=False):
        return {"found": 3, "new": 2, "jobs": []}


def test_run_discovery_cycle_wraps_a_run(tmp_db):
    register(_FakeSource())
    profile = {"keywords": "x", "location": "y", "pages": 1}

    res = runner.run_discovery_cycle(profile, source_name="fake", score=False)
    assert res["status"] == RunStatus.DONE

    run = repo.get_run(res["run_id"])
    assert run["status"] == RunStatus.DONE
    assert run["jobs_found"] == 3 and run["jobs_new"] == 2
    assert "found=3 new=2" in run["log"]


def test_run_cycle_fails_loudly_on_blocked_scrape(tmp_db):
    class _Blocked:
        name = "blocked-src"

        def discover(self, **_):
            return {"found": 0, "new": 0, "jobs": [], "health": "blocked"}

    register(_Blocked())
    res = runner.run_discovery_cycle({"keywords": "x", "location": "y"}, source_name="blocked-src", score=False)
    assert res["status"] == RunStatus.FAILED
    assert repo.get_run(res["run_id"])["status"] == RunStatus.FAILED
    assert "scrape.blocked" in [e["type"] for e in repo.fetch_unprocessed_events()]


def test_run_discovery_cycle_records_failure(tmp_db):
    class _Boom:
        name = "boom"

        def discover(self, **_):
            raise RuntimeError("blocked")

    register(_Boom())
    res = runner.run_discovery_cycle({"keywords": "x", "location": "y"}, source_name="boom", score=False)
    assert res["status"] == RunStatus.FAILED
    assert repo.get_run(res["run_id"])["status"] == RunStatus.FAILED


# ---------- scheduler wiring ----------


def test_build_scheduler_registers_both_jobs():
    from job_hunt.worker.scheduler import build_scheduler

    sched = build_scheduler()
    ids = {j.id for j in sched.get_jobs()}
    assert {"discovery", "dispatch"} <= ids
