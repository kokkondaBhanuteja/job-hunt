"""Tests for the RemoteOK plugin (API mocked) + cross-source dedup."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.enums import JobState
from job_hunt.plugins import remoteok
from job_hunt.sources.dedup import dedup_hash
from job_hunt.storage import repo

CANNED = [
    {"legal": "See https://remoteok.com/terms"},  # metadata element — must be skipped
    {"id": 1, "position": "Backend Engineer", "company": "Acme",
     "tags": ["backend", "python"], "location": "Remote",
     "description": "<p>Build <b>APIs</b> in Python and Postgres.</p>",
     "url": "https://remoteok.com/l/1", "date": "2026-06-01"},
    {"id": 2, "position": "Frontend Designer", "company": "Beta",
     "tags": ["design", "figma"], "location": "Remote",
     "description": "<p>Design UIs</p>", "url": "https://remoteok.com/l/2", "date": "2026-06-02"},
]


def _mock(monkeypatch):
    monkeypatch.setattr(remoteok, "_fetch", lambda url=remoteok.REMOTEOK_API: CANNED)


def test_registered():
    assert "remoteok" in plugins.available_sources()


def test_discover_filters_inserts_and_enriches(tmp_db, monkeypatch):
    _mock(monkeypatch)
    result = plugins.get_source("remoteok").discover(keyword="backend python", location="remote")

    # Only the backend job matches "backend python"; the designer is filtered out.
    assert result == {"found": 1, "new": 1, "jobs": result["jobs"]}
    assert len(result["jobs"]) == 1

    rows = repo.raw_select("SELECT id, state, description_full FROM jobs WHERE source='remoteok'")
    assert len(rows) == 1
    assert rows[0]["state"] == JobState.ENRICHED           # full JD present → straight to ENRICHED
    assert "Build" in rows[0]["description_full"] and "<b>" not in rows[0]["description_full"]


def test_cross_source_dedup_with_naukri(tmp_db, monkeypatch):
    _mock(monkeypatch)
    # A Naukri listing for the same role already exists (same canonical key).
    tmp_db.insert_job_if_new(
        dedup_hash=dedup_hash("Acme", "Backend Engineer", "Remote"),
        source="naukri", source_job_id=None, title="Sr. Backend Engineer", company="Acme",
        location="Remote", description="from naukri", apply_url="https://naukri/x", posted_date=None,
    )
    result = plugins.get_source("remoteok").discover(keyword="backend")
    # Found on RemoteOK, but it's a duplicate of the Naukri row → nothing new inserted.
    assert result["found"] == 1
    assert result["new"] == 0


def test_dry_run_inserts_nothing(tmp_db, monkeypatch):
    _mock(monkeypatch)
    result = plugins.get_source("remoteok").discover(keyword="backend", dry_run=True)
    assert result["found"] == 1 and result["new"] == 0
    assert repo.raw_select("SELECT count(*) AS c FROM jobs")[0]["c"] == 0
