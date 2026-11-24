"""Tests for the Himalayas plugin (JSON search API mocked — no network)."""
from __future__ import annotations

from typing import Any

import pytest

from job_hunt import plugins
from job_hunt.plugins import himalayas


def _row(n: int, restrictions: list[str] | None) -> dict[str, Any]:
    return {
        "title": f"Backend Engineer {n}", "companyName": f"Co {n}",
        "applicationLink": f"https://himalayas.app/jobs/{n}", "guid": f"guid-{n}",
        "description": "<p>Build <b>APIs</b>.</p>", "pubDate": 1795107887,
        "locationRestrictions": restrictions, "seniority": ["Mid-level"],
        "timezoneRestrictions": [5.5],
    }


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    monkeypatch.setattr(himalayas, "HIMALAYAS_PAGE_DELAY_S", 0)


def test_registered():
    assert "himalayas" in plugins.available_sources()


def test_searches_for_india_eligible_jobs_with_the_keyword(monkeypatch):
    calls: list[dict[str, Any]] = []

    def _spy(params: dict[str, Any]) -> dict[str, Any]:
        calls.append(params)
        return {"totalCount": 1, "jobs": [_row(1, ["India"])]}

    monkeypatch.setattr(himalayas, "_fetch", _spy)
    himalayas.HimalayasSource().discover(keyword="backend engineer", dry_run=True)
    assert calls == [{"q": "backend engineer", "page": 1, "country": "IN"}]


@pytest.mark.parametrize(("restrictions", "expected"), [
    (["India"], "Remote - India"),
    (["Egypt", "India", "Pakistan"], "Remote - Egypt, India, Pakistan"),
    ([], "Remote - Worldwide"),
    (None, "Remote - Worldwide"),
])
def test_location_from_restrictions(monkeypatch, restrictions, expected):
    monkeypatch.setattr(himalayas, "_fetch",
                        lambda params: {"totalCount": 1, "jobs": [_row(1, restrictions)]})
    job = himalayas.HimalayasSource().discover(keyword="backend", dry_run=True)["jobs"][0]
    assert job["location"] == expected
    assert (job["title"], job["company"]) == ("Backend Engineer 1", "Co 1")


def test_pages_until_total_or_max(monkeypatch):
    monkeypatch.setattr(himalayas, "HIMALAYAS_MAX_PAGES", 3)
    pages: list[int] = []

    def _spy(params: dict[str, Any]) -> dict[str, Any]:
        pages.append(params["page"])
        return {"totalCount": 40, "jobs": [_row(i, ["India"]) for i in range(20)]}

    monkeypatch.setattr(himalayas, "_fetch", _spy)
    result = himalayas.HimalayasSource().discover(keyword="backend", dry_run=True)
    assert pages == [1, 2]  # stops once page * 20 >= totalCount (40)
    assert result["found"] == 40


def test_fetch_failure_returns_what_it_has(monkeypatch):
    def _boom(params: dict[str, Any]) -> dict[str, Any]:
        if params["page"] == 2:
            raise RuntimeError("429")
        return {"totalCount": 100, "jobs": [_row(1, ["India"])]}

    monkeypatch.setattr(himalayas, "HIMALAYAS_MAX_PAGES", 3)
    monkeypatch.setattr(himalayas, "_fetch", _boom)
    assert himalayas.HimalayasSource().discover(keyword="backend", dry_run=True)["found"] == 1


def test_posted_date_converted_from_unix_seconds():
    assert himalayas._posted(86400) == "1970-01-02"  # one day after the Unix epoch, in UTC
    assert himalayas._posted(1795107887) == "2026-11-19"
    assert himalayas._posted(None) is None
