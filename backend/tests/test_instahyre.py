"""Tests for the Instahyre plugin (job search mocked — no network)."""
from __future__ import annotations

from typing import Any

import pytest

from job_hunt import plugins
from job_hunt.plugins import instahyre


def _row(n: int, locations: str = "Bangalore") -> dict[str, Any]:
    return {
        "id": 400000 + n,
        "title": f"SDE {n} (Backend)",
        "locations": locations,
        "public_url": f"https://www.instahyre.com/job-{400000 + n}-sde-backend/",
        "keywords": ["Java", "Microservices", "REST"],
        "reviewed_at": "2026-11-20T10:00:00Z",
        "employer": {"company_name": "Aspora", "company_tagline": "Global finance",
                     "instahyre_note": "Builds cross-border payments."},
    }


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    monkeypatch.setattr(instahyre, "INSTAHYRE_PAGE_DELAY_S", 0)


def test_registered():
    assert "instahyre" in plugins.available_sources()


@pytest.mark.parametrize(("keyword", "skills"), [
    ("backend engineer", "backend"), ("node.js", "node.js"), ("Senior Java Developer", "Java"),
    ("software engineer", "software"),
])
def test_profile_keyword_maps_to_skills_filter(keyword, skills):
    assert instahyre._skills_query(keyword) == skills


@pytest.mark.parametrize(("raw", "expected"), [
    ("Bangalore", "Bangalore, India"), ("Bangalore,Hyderabad,Pune", "Bangalore,Hyderabad,Pune, India"),
    ("Work From Home", "Work From Home, India"), ("", "India"), (None, "India"),
    ("Remote, India", "Remote, India"),
])
def test_locations_marked_as_india(raw, expected):
    assert instahyre._location(raw) == expected


def test_parses_jobs_and_sends_skills_filter(monkeypatch):
    calls: list[dict[str, Any]] = []

    def _spy(params: dict[str, Any]) -> dict[str, Any]:
        calls.append(params)
        return {"meta": {"next": None}, "objects": [_row(1)]}

    monkeypatch.setattr(instahyre, "_fetch", _spy)
    result = instahyre.InstahyreSource().discover(keyword="backend engineer", dry_run=True)
    assert calls == [{"limit": 35, "offset": 0, "skills": "backend"}]
    assert result["jobs"] == [{
        "title": "SDE 1 (Backend)", "company": "Aspora", "location": "Bangalore, India",
        "apply_url": "https://www.instahyre.com/job-400001-sde-backend/",
    }]


def test_pages_politely_and_stops_at_max(monkeypatch):
    monkeypatch.setattr(instahyre, "INSTAHYRE_MAX_PAGES", 2)
    offsets: list[int] = []

    def _spy(params: dict[str, Any]) -> dict[str, Any]:
        offsets.append(params["offset"])
        return {"meta": {"next": "/api/v1/job_search?offset=..."}, "objects": [_row(params["offset"])]}

    monkeypatch.setattr(instahyre, "_fetch", _spy)
    instahyre.InstahyreSource().discover(keyword="backend", dry_run=True)
    assert offsets == [0, 35]


def test_stops_at_first_error_and_keeps_earlier_jobs(monkeypatch):
    monkeypatch.setattr(instahyre, "INSTAHYRE_MAX_PAGES", 3)

    def _spy(params: dict[str, Any]) -> dict[str, Any]:
        if params["offset"] > 0:
            raise RuntimeError("403 blocked")
        return {"meta": {"next": "x"}, "objects": [_row(1)]}

    monkeypatch.setattr(instahyre, "_fetch", _spy)
    assert instahyre.InstahyreSource().discover(keyword="backend", dry_run=True)["found"] == 1


def test_description_carries_skills_and_company_note():
    text = instahyre._description(_row(1), "Aspora")
    assert "SDE 1 (Backend) at Aspora" in text
    assert "Skills: Java, Microservices, REST" in text
    assert "Builds cross-border payments." in text


def test_saved_job_passes_the_india_location_filter(tmp_db, monkeypatch):
    from job_hunt.sources import location
    monkeypatch.setattr(location, "JOB_LOCATION_FILTER", "india-remote")
    monkeypatch.setattr(instahyre, "_fetch",
                        lambda params: {"meta": {"next": None}, "objects": [_row(1, "Work From Home")]})
    result = instahyre.InstahyreSource().discover(keyword="backend")
    assert result["new"] == 1
