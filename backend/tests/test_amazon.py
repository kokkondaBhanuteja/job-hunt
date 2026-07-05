"""Tests for the Amazon Jobs plugin (API mocked — no network)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.enums import JobState
from job_hunt.plugins import amazon
from job_hunt.storage import repo

# Canned response matching the confirmed Amazon search.json shape.
CANNED: dict = {
    "jobs": [
        {
            "id": "86585149-2beb-4d93-9677-994576b0b343",
            "id_icims": "10465706",
            "title": "Software Development Engineer, AWS",
            "company_name": "Amazon Web Services",
            "location": "WA, Seattle",
            "normalized_location": "Seattle, Washington, USA",
            "job_path": "/en/jobs/10465706/software-development-engineer-aws",
            "posted_date": "July 3, 2026",
            "description": "<p>Build <b>scalable</b> AWS services.</p>",
            "description_short": "Build scalable AWS services.",
            "basic_qualifications": "BS in CS, 3+ years",
        },
        {
            "id": "99999999-0000-0000-0000-000000000001",
            "id_icims": "20001234",
            "title": "Backend Engineer, Prime Video",
            "company_name": "Amazon",
            "location": "CA, Vancouver",
            "normalized_location": "Vancouver, BC, CAN",
            "job_path": "/en/jobs/20001234/backend-engineer-prime-video",
            "posted_date": "July 1, 2026",
            "description": "<p>Deliver <i>streaming</i> at scale.</p>",
            "description_short": "Deliver streaming at scale.",
            "basic_qualifications": "BS in CS, 5+ years",
        },
    ]
}


def _mock(monkeypatch) -> None:
    """Monkeypatch _fetch to return canned data."""
    monkeypatch.setattr(amazon, "_fetch", lambda keyword, location, result_limit=20: CANNED)


def test_registered() -> None:
    """Amazon should be in the available sources registry."""
    assert "amazon" in plugins.available_sources()


def test_discover_dry_run_finds_jobs(tmp_db, monkeypatch) -> None:
    """discover(dry_run=True) returns found>=1, correct title and apply_url, no DB rows."""
    _mock(monkeypatch)

    result = plugins.get_source("amazon").discover(keyword="engineer", dry_run=True)

    assert result["found"] >= 1
    assert result["new"] == 0
    assert result["jobs"][0]["title"] == "Software Development Engineer, AWS"
    assert result["jobs"][0]["apply_url"] == (
        "https://www.amazon.jobs/en/jobs/10465706/software-development-engineer-aws"
    )

    rows = repo.raw_select("SELECT count(*) AS c FROM jobs WHERE source='amazon'")
    assert rows[0]["c"] == 0


def test_discover_inserts_and_enriches(tmp_db, monkeypatch) -> None:
    """Discover should insert jobs, strip HTML, and mark them ENRICHED."""
    _mock(monkeypatch)

    result = plugins.get_source("amazon").discover(keyword="engineer")

    assert result["found"] == 2
    assert result["new"] == 2

    rows = repo.raw_select("SELECT state, description_full FROM jobs WHERE source='amazon' ORDER BY id")
    assert len(rows) == 2
    assert rows[0]["state"] == JobState.ENRICHED
    # HTML must be stripped
    assert "scalable" in rows[0]["description_full"]
    assert "<b>" not in rows[0]["description_full"]


def test_apply_url_built_from_job_path(tmp_db, monkeypatch) -> None:
    """apply_url should be amazon.jobs base + job_path."""
    _mock(monkeypatch)

    result = plugins.get_source("amazon").discover(keyword="engineer", dry_run=True)

    assert result["jobs"][1]["apply_url"] == (
        "https://www.amazon.jobs/en/jobs/20001234/backend-engineer-prime-video"
    )


def test_http_error_returns_empty(tmp_db, monkeypatch) -> None:
    """An HTTP error from _fetch should return empty result without raising."""
    import httpx

    def _fail(*a, **kw):
        raise httpx.HTTPStatusError("404", request=None, response=None)

    monkeypatch.setattr(amazon, "_fetch", _fail)

    result = plugins.get_source("amazon").discover(keyword="engineer")
    assert result == {"found": 0, "new": 0, "jobs": []}


def test_missing_title_skipped(tmp_db, monkeypatch) -> None:
    """Items without a title field should be silently skipped."""
    canned = {"jobs": [{"id_icims": "999", "company_name": "Amazon", "location": "Remote"}]}
    monkeypatch.setattr(amazon, "_fetch", lambda *a, **k: canned)

    result = plugins.get_source("amazon").discover(keyword="engineer", dry_run=True)
    assert result["found"] == 0
