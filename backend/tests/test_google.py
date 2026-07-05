"""Tests for the Google Careers plugin (API mocked — no network)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.enums import JobState
from job_hunt.plugins import google
from job_hunt.storage import repo

# Canned response matching the documented Google Careers v3 API shape.
# (Endpoint verified to exist; field names from task spec + graceful fallback.)
CANNED: dict = {
    "jobs": [
        {
            "id": "jobs/10000000000000001",
            "title": "Software Engineer, Backend",
            "company_name": "Google",
            "locations": [{"display": "Mountain View, CA, USA"}],
            "apply_url": "https://careers.google.com/jobs/results/10000000000000001/",
            "publish_date": "2026-07-01T00:00:00Z",
            "description": "<p>Build <b>reliable</b> backend systems.</p>",
            "summary": "Build reliable backend systems.",
        },
        {
            "id": "jobs/10000000000000002",
            "title": "Site Reliability Engineer",
            "company_name": "Google",
            "locations": [{"display": "Bangalore, Karnataka, India"}],
            "apply_url": "https://careers.google.com/jobs/results/10000000000000002/",
            "publish_date": "2026-06-28T00:00:00Z",
            "description": "<p>Ensure <em>uptime</em> and reliability.</p>",
            "summary": "Ensure uptime and reliability.",
        },
    ]
}


def _mock(monkeypatch) -> None:
    """Monkeypatch _fetch to return canned data."""
    monkeypatch.setattr(google, "_fetch", lambda keyword, location, page_size=20: CANNED)


def test_registered() -> None:
    """Google should be in the available sources registry."""
    assert "google" in plugins.available_sources()


def test_discover_dry_run_finds_jobs(tmp_db, monkeypatch) -> None:
    """discover(dry_run=True) returns found>=1, correct title and apply_url, no DB rows."""
    _mock(monkeypatch)

    result = plugins.get_source("google").discover(keyword="engineer", dry_run=True)

    assert result["found"] >= 1
    assert result["new"] == 0
    assert result["jobs"][0]["title"] == "Software Engineer, Backend"
    assert result["jobs"][0]["apply_url"] == (
        "https://careers.google.com/jobs/results/10000000000000001/"
    )

    rows = repo.raw_select("SELECT count(*) AS c FROM jobs WHERE source='google'")
    assert rows[0]["c"] == 0


def test_discover_inserts_and_enriches(tmp_db, monkeypatch) -> None:
    """Discover should insert jobs, strip HTML, and mark them ENRICHED."""
    _mock(monkeypatch)

    result = plugins.get_source("google").discover(keyword="engineer")

    assert result["found"] == 2
    assert result["new"] == 2

    rows = repo.raw_select("SELECT state, description_full FROM jobs WHERE source='google' ORDER BY id")
    assert len(rows) == 2
    assert rows[0]["state"] == JobState.ENRICHED
    # HTML must be stripped
    assert "reliable" in rows[0]["description_full"]
    assert "<b>" not in rows[0]["description_full"]


def test_location_from_locations_array(tmp_db, monkeypatch) -> None:
    """Location should be parsed from the first element of the locations list."""
    _mock(monkeypatch)

    result = plugins.get_source("google").discover(keyword="engineer", dry_run=True)

    assert result["jobs"][0]["location"] == "Mountain View, CA, USA"
    assert result["jobs"][1]["location"] == "Bangalore, Karnataka, India"


def test_http_error_returns_empty(tmp_db, monkeypatch) -> None:
    """An HTTP error from _fetch should return empty result without raising."""
    import httpx

    def _fail(*a, **kw):
        raise httpx.HTTPStatusError("404", request=None, response=None)

    monkeypatch.setattr(google, "_fetch", _fail)

    result = plugins.get_source("google").discover(keyword="engineer")
    assert result == {"found": 0, "new": 0, "jobs": []}


def test_missing_title_skipped(tmp_db, monkeypatch) -> None:
    """Items without a title field should be silently skipped."""
    canned = {"jobs": [{"id": "999", "company_name": "Google", "locations": []}]}
    monkeypatch.setattr(google, "_fetch", lambda *a, **k: canned)

    result = plugins.get_source("google").discover(keyword="engineer", dry_run=True)
    assert result["found"] == 0
