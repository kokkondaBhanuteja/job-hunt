"""Tests for the Adzuna plugin (API mocked)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.enums import JobState
from job_hunt.plugins import adzuna
from job_hunt.storage import repo

CANNED = {
    "results": [
        {
            "id": 1,
            "title": "Backend Engineer",
            "company": {"display_name": "Acme"},
            "location": {"display_name": "Bangalore"},
            "description": "<p>Build <b>APIs</b> in Python.</p>",
            "redirect_url": "https://example.com/job/1",
            "created": "2026-01-01",
        },
        {
            "id": 2,
            "title": "Frontend Developer",
            "company": {"display_name": "Beta"},
            "location": {"display_name": "Remote"},
            "description": "<p>React and TypeScript</p>",
            "redirect_url": "https://example.com/job/2",
            "created": "2026-01-02",
        },
    ]
}


def _mock(monkeypatch):
    """Mock _fetch to return canned data."""
    monkeypatch.setattr(
        adzuna,
        "_fetch",
        lambda country, what, where, page, app_id, app_key: CANNED,
    )


def test_registered():
    """Adzuna should be in available sources."""
    assert "adzuna" in plugins.available_sources()


def test_discover_inserts_and_enriches(tmp_db, monkeypatch):
    """Discover should insert jobs with full JD and mark as ENRICHED."""
    _mock(monkeypatch)
    monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")

    result = plugins.get_source("adzuna").discover(
        keyword="backend", location="bangalore"
    )

    # Two jobs discovered
    assert result["found"] == 2
    assert result["new"] == 2
    assert len(result["jobs"]) == 2

    # Check first job is properly parsed
    assert result["jobs"][0]["title"] == "Backend Engineer"
    assert result["jobs"][0]["company"] == "Acme"
    assert result["jobs"][0]["location"] == "Bangalore"
    assert result["jobs"][0]["apply_url"] == "https://example.com/job/1"

    # Check DB insertion and enrichment
    rows = repo.raw_select("SELECT id, state, description_full FROM jobs WHERE source='adzuna'")
    assert len(rows) == 2
    assert rows[0]["state"] == JobState.ENRICHED
    # HTML should be stripped
    assert "Build" in rows[0]["description_full"]
    assert "<b>" not in rows[0]["description_full"]


def test_missing_credentials_returns_empty(tmp_db, monkeypatch):
    """Missing app_id/key should return empty result without crash."""
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)

    result = plugins.get_source("adzuna").discover(keyword="backend")

    assert result == {"found": 0, "new": 0, "jobs": []}


def test_dry_run_inserts_nothing(tmp_db, monkeypatch):
    """dry_run=True should not insert any jobs."""
    _mock(monkeypatch)
    monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")

    result = plugins.get_source("adzuna").discover(
        keyword="backend", dry_run=True
    )

    assert result["found"] == 2
    assert result["new"] == 0
    # Check DB is empty
    rows = repo.raw_select("SELECT count(*) AS c FROM jobs")
    assert rows[0]["c"] == 0


def test_missing_optional_fields(tmp_db, monkeypatch):
    """Jobs with missing optional fields should still be stored."""
    canned_sparse = {
        "results": [
            {
                "id": 3,
                "title": "Data Analyst",
                # company is None
                "location": None,  # location is None
                # description is missing
                "redirect_url": "https://example.com/job/3",
                "created": "2026-01-03",
            }
        ]
    }
    monkeypatch.setattr(
        adzuna,
        "_fetch",
        lambda country, what, where, page, app_id, app_key: canned_sparse,
    )
    monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")

    result = plugins.get_source("adzuna").discover(keyword="data", location="bangalore")

    assert result["found"] == 1
    assert result["new"] == 1
    # Defaults should be applied
    assert result["jobs"][0]["company"] == "Unknown"
    assert result["jobs"][0]["location"] == "bangalore"  # fallback to input location
