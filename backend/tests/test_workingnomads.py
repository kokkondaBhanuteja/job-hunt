"""Tests for the Working Nomads plugin (JSON API mocked — no network)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.plugins import workingnomads

CANNED_JOBS: list[dict] = [
    {
        "title": "Senior Python Developer",
        "company_name": "Acme Corp",
        "url": "https://www.workingnomads.com/jobs?id=1",
        "description": "<p>Build <b>APIs</b> in Python.</p>",
        "pub_date": "2026-01-10T00:00:00Z",
        "location": "Europe, LATAM, APAC, the U.S., Canada",
        "category_name": "Development",
        "tags": "python,django",
    },
    {
        "title": "React Frontend Engineer",
        "company_name": "Beta Ltd",
        "url": "https://www.workingnomads.com/jobs?id=2",
        "description": "<p>Build UIs with React.</p>",
        "pub_date": "2026-01-11T00:00:00Z",
        "location": "",
        "category_name": "Development",
        "tags": "react",
    },
]


def test_registered():
    """WorkingNomads should appear in available_sources."""
    assert "workingnomads" in plugins.available_sources()


def test_uses_the_json_api_not_the_retired_rss():
    assert workingnomads.WORKINGNOMADS_API.endswith("/api/exposed_jobs/")


def test_discover_keyword_filter_dry_run(monkeypatch):
    """Keyword filter should match python job and skip react job; dry_run skips DB."""
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: CANNED_JOBS)

    result = workingnomads.WorkingNomadsSource().discover(keyword="python", dry_run=True)

    titles = [j["title"] for j in result["jobs"]]
    assert titles == ["Senior Python Developer"]
    assert result["new"] == 0


def test_fields_parsed_with_real_location(monkeypatch):
    """Fields come from the JSON row; location is the job's own region, marked remote."""
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: CANNED_JOBS)

    job = workingnomads.WorkingNomadsSource().discover(keyword="python", dry_run=True)["jobs"][0]

    assert job["title"] == "Senior Python Developer"
    assert job["company"] == "Acme Corp"
    assert job["apply_url"] == "https://www.workingnomads.com/jobs?id=1"
    assert job["location"] == "Remote - Europe, LATAM, APAC, the U.S., Canada"


def test_missing_location_falls_back_to_profile_location(monkeypatch):
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: CANNED_JOBS)
    jobs = workingnomads.WorkingNomadsSource().discover(keyword="react", dry_run=True)["jobs"]
    assert jobs[0]["location"] == "remote"


def test_html_stripped():
    """HTML tags in description should be stripped."""
    from job_hunt.plugins._persist import strip_html
    stripped = strip_html("<p>Build <b>APIs</b> in Python.</p>")
    assert "<b>" not in stripped
    assert "APIs" in stripped


def test_empty_keyword_returns_all(monkeypatch):
    """Empty keyword should return all jobs."""
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: CANNED_JOBS)
    assert workingnomads.WorkingNomadsSource().discover(keyword="", dry_run=True)["found"] == 2


def test_bad_row_does_not_crash(monkeypatch):
    """A malformed row should be skipped without crashing the batch."""
    rows = [{}, {"title": None}, {"title": "Python Backend Dev", "url": "https://x/3",
                                  "description": "Python work here"}]
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: rows)
    result = workingnomads.WorkingNomadsSource().discover(keyword="python", dry_run=True)
    assert [j["title"] for j in result["jobs"]] == ["Python Backend Dev"]
