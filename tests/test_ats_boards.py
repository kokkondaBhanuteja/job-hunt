"""Tests for Greenhouse + Lever source plugins (APIs mocked)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.enums import JobState
from job_hunt.plugins import greenhouse, lever
from job_hunt.storage import repo

GH_JOBS = [
    {"id": 1, "title": "Backend Engineer", "location": {"name": "Remote"},
     "content": "<p>Build <b>APIs</b> in Go</p>",
     "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "updated_at": "2026-06-01"},
    {"id": 2, "title": "Frontend Engineer", "location": {"name": "New York"},
     "content": "<p>UI work</p>", "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
     "updated_at": "2026-06-02"},
]

LV_JOBS = [
    {"id": "a1", "text": "Platform Engineer", "categories": {"location": "Remote"},
     "descriptionPlain": "Own the deploy pipeline.", "hostedUrl": "https://jobs.lever.co/acme/a1",
     "createdAt": 1717200000000},
]


def test_both_registered():
    assert {"greenhouse", "lever"} <= set(plugins.available_sources())


def test_greenhouse_discovers_and_enriches(tmp_db, monkeypatch):
    monkeypatch.setattr(greenhouse, "_fetch", lambda board: GH_JOBS)
    result = plugins.get_source("greenhouse").discover(keyword="acme", location="remote")
    # Only the Remote job matches the location filter.
    assert result == {"found": 1, "new": 1, "jobs": result["jobs"]}

    rows = repo.raw_select("SELECT state, description_full FROM jobs WHERE source='greenhouse'")
    assert len(rows) == 1
    assert rows[0]["state"] == JobState.ENRICHED
    assert "Build" in rows[0]["description_full"] and "<b>" not in rows[0]["description_full"]


def test_lever_discovers_and_enriches(tmp_db, monkeypatch):
    monkeypatch.setattr(lever, "_fetch", lambda company: LV_JOBS)
    result = plugins.get_source("lever").discover(keyword="acme")
    assert result["found"] == 1 and result["new"] == 1

    rows = repo.raw_select("SELECT state, description_full FROM jobs WHERE source='lever'")
    assert rows[0]["state"] == JobState.ENRICHED
    assert rows[0]["description_full"] == "Own the deploy pipeline."


def test_greenhouse_dry_run_inserts_nothing(tmp_db, monkeypatch):
    monkeypatch.setattr(greenhouse, "_fetch", lambda board: GH_JOBS)
    result = plugins.get_source("greenhouse").discover(keyword="acme", dry_run=True)
    assert result["found"] == 2 and result["new"] == 0
    assert repo.raw_select("SELECT count(*) AS c FROM jobs")[0]["c"] == 0
