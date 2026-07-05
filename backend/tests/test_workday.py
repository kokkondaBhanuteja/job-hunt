"""Tests for the Workday plugin (network mocked — no real HTTP)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.plugins import workday

_KEYWORD = "qualcomm.wd5.myworkdayjobs.com/External"

_CANNED_RESPONSE: dict = {
    "total": 1,
    "jobPostings": [
        {
            "title": "Senior Engineer",
            "locationsText": "Dubai, UAE",
            "externalPath": "/job/Dubai/Senior-Engineer_123",
            "postedOn": "Posted Today",
            "bulletFields": ["123"],
        }
    ],
}


def test_registered():
    """Workday should appear in available_sources."""
    assert "workday" in plugins.available_sources()


def test_discover_dry_run(monkeypatch):
    """discover() should parse all fields correctly and return found==1 in dry_run."""
    monkeypatch.setattr(workday, "_last_fetch", {})
    monkeypatch.setattr(workday, "WORKDAY_MIN_INTERVAL_S", 0)
    monkeypatch.setattr(workday, "_fetch", lambda *a, **k: _CANNED_RESPONSE)

    result = workday.WorkdaySource().discover(keyword=_KEYWORD, dry_run=True)

    assert result["found"] == 1
    assert result["new"] == 0
    job = result["jobs"][0]
    assert job["title"] == "Senior Engineer"
    assert job["location"] == "Dubai, UAE"
    assert job["apply_url"] == (
        "https://qualcomm.wd5.myworkdayjobs.com/External"
        "/job/Dubai/Senior-Engineer_123"
    )


def test_token_parsing(monkeypatch):
    """discover() should parse host/tenant/site from the careers-site spec."""
    monkeypatch.setattr(workday, "_last_fetch", {})
    monkeypatch.setattr(workday, "WORKDAY_MIN_INTERVAL_S", 0)

    captured: dict = {}

    def _spy(host: str, tenant: str, site: str, search_text: str) -> dict:
        captured.update(host=host, tenant=tenant, site=site)
        return _CANNED_RESPONSE

    monkeypatch.setattr(workday, "_fetch", _spy)

    workday.WorkdaySource().discover(keyword=_KEYWORD, dry_run=True)

    assert captured["host"] == "qualcomm.wd5.myworkdayjobs.com"
    assert captured["tenant"] == "qualcomm"
    assert captured["site"] == "External"


def test_token_parsing_with_https_scheme(monkeypatch):
    """An https:// prefix on the keyword should be accepted and stripped."""
    monkeypatch.setattr(workday, "_last_fetch", {})
    monkeypatch.setattr(workday, "WORKDAY_MIN_INTERVAL_S", 0)

    captured: dict = {}

    def _spy(host: str, tenant: str, site: str, search_text: str) -> dict:
        captured.update(host=host, tenant=tenant, site=site)
        return _CANNED_RESPONSE

    monkeypatch.setattr(workday, "_fetch", _spy)

    workday.WorkdaySource().discover(
        keyword="https://qualcomm.wd5.myworkdayjobs.com/External", dry_run=True
    )

    assert captured["tenant"] == "qualcomm"
    assert captured["site"] == "External"


def test_malformed_token_returns_empty_no_crash(monkeypatch):
    """A keyword that is not a Workday careers-site spec returns empty without raising."""
    monkeypatch.setattr(workday, "_last_fetch", {})
    monkeypatch.setattr(workday, "WORKDAY_MIN_INTERVAL_S", 0)

    result = workday.WorkdaySource().discover(keyword="not-a-workday-site", dry_run=True)

    assert result == {"found": 0, "new": 0, "jobs": []}


def test_malformed_token_plain_domain_no_crash(monkeypatch):
    """A keyword that looks like a domain but not Workday returns empty without raising."""
    monkeypatch.setattr(workday, "_last_fetch", {})
    monkeypatch.setattr(workday, "WORKDAY_MIN_INTERVAL_S", 0)

    result = workday.WorkdaySource().discover(keyword="example.com/jobs", dry_run=True)

    assert result == {"found": 0, "new": 0, "jobs": []}


def test_throttle_skips_second_fetch(monkeypatch):
    """With a non-zero interval, an immediate second discover for the same token skips _fetch."""
    monkeypatch.setattr(workday, "_last_fetch", {})
    monkeypatch.setattr(workday, "WORKDAY_MIN_INTERVAL_S", 99999)

    call_count = 0

    def _spy(*a: object, **k: object) -> dict:
        nonlocal call_count
        call_count += 1
        return _CANNED_RESPONSE

    monkeypatch.setattr(workday, "_fetch", _spy)

    src = workday.WorkdaySource()
    src.discover(keyword=_KEYWORD, dry_run=True)
    result2 = src.discover(keyword=_KEYWORD, dry_run=True)

    assert call_count == 1
    assert result2 == {"found": 0, "new": 0, "jobs": []}


def test_missing_title_skipped(monkeypatch):
    """A posting with no title should be skipped without crashing."""
    monkeypatch.setattr(workday, "_last_fetch", {})
    monkeypatch.setattr(workday, "WORKDAY_MIN_INTERVAL_S", 0)

    canned = {
        "total": 2,
        "jobPostings": [
            {"title": None, "externalPath": "/job/bad"},
            {
                "title": "Good Job",
                "locationsText": "Remote",
                "externalPath": "/job/good",
                "bulletFields": [],
            },
        ],
    }
    monkeypatch.setattr(workday, "_fetch", lambda *a, **k: canned)

    result = workday.WorkdaySource().discover(keyword=_KEYWORD, dry_run=True)

    assert result["found"] == 1
    assert result["jobs"][0]["title"] == "Good Job"
