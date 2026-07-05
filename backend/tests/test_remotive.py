"""Tests for the Remotive plugin (API mocked — no network)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.plugins import remotive

CANNED_PAYLOAD: dict = {
    "jobs": [
        {
            "id": 101,
            "title": "Senior Python Engineer",
            "company_name": "Acme Corp",
            "candidate_required_location": "Worldwide",
            "url": "https://remotive.com/remote-jobs/software-dev/101",
            "description": "<p>Build <b>APIs</b> in Python and Django.</p>",
            "tags": ["python", "django", "remote"],
            "publication_date": "2026-01-10T00:00:00",
        },
        {
            "id": 102,
            "title": "React Frontend Developer",
            "company_name": "Beta Ltd",
            "candidate_required_location": "Europe",
            "url": "https://remotive.com/remote-jobs/software-dev/102",
            "description": "<p>Build UIs with <em>React</em>.</p>",
            "tags": ["react", "javascript"],
            "publication_date": "2026-01-11T00:00:00",
        },
    ]
}


def test_registered():
    """Remotive should appear in available_sources."""
    assert "remotive" in plugins.available_sources()


def test_discover_keyword_filter_dry_run(monkeypatch):
    """Keyword filter should match python job and skip react job; dry_run skips DB."""
    monkeypatch.setattr(remotive, "_fetch", lambda url: CANNED_PAYLOAD)

    result = remotive.RemotiveSource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
    titles = [j["title"] for j in result["jobs"]]
    assert any("Python" in t for t in titles)
    # React job should be filtered out
    assert not any("React" in t for t in titles)
    # dry_run → nothing persisted
    assert result["new"] == 0


def test_html_stripped(monkeypatch):
    """HTML tags should be stripped from the description."""
    monkeypatch.setattr(remotive, "_fetch", lambda url: CANNED_PAYLOAD)

    result = remotive.RemotiveSource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
    # We check via the DB-less path; strip_html is exercised in persist path,
    # but we can also verify the job dict doesn't contain the raw HTML tags.
    # The description is only stored via persist_full_jd_job, so verify strip_html:
    from job_hunt.plugins._persist import strip_html
    raw = "<p>Build <b>APIs</b> in Python and Django.</p>"
    stripped = strip_html(raw)
    assert "<b>" not in stripped
    assert "APIs" in stripped


def test_fields_parsed(monkeypatch):
    """All key fields should be present and correct."""
    monkeypatch.setattr(remotive, "_fetch", lambda url: CANNED_PAYLOAD)

    result = remotive.RemotiveSource().discover(keyword="python", dry_run=True)

    job = result["jobs"][0]
    assert job["title"] == "Senior Python Engineer"
    assert job["company"] == "Acme Corp"
    assert job["location"] == "Worldwide"
    assert job["apply_url"] == "https://remotive.com/remote-jobs/software-dev/101"


def test_empty_keyword_returns_all(monkeypatch):
    """Empty keyword should return all jobs."""
    monkeypatch.setattr(remotive, "_fetch", lambda url: CANNED_PAYLOAD)

    result = remotive.RemotiveSource().discover(keyword="", dry_run=True)

    assert result["found"] == 2


def test_bad_item_does_not_crash(monkeypatch):
    """A malformed job row should be skipped without crashing the batch."""
    payload = {
        "jobs": [
            None,  # bad item
            {
                "id": 103,
                "title": "Python Backend Dev",
                "company_name": "GoodCo",
                "candidate_required_location": "Remote",
                "url": "https://remotive.com/103",
                "description": "Python work",
                "tags": ["python"],
                "publication_date": "2026-01-12T00:00:00",
            },
        ]
    }
    monkeypatch.setattr(remotive, "_fetch", lambda url: payload)

    result = remotive.RemotiveSource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
