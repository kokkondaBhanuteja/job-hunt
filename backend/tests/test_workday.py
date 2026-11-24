"""Tests for the Workday plugin (network mocked — no real HTTP)."""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from job_hunt import plugins
from job_hunt.plugins import workday


@pytest.fixture(autouse=True)
def _legacy_unfiltered(monkeypatch):
    """Existing tests exercise the unfiltered path; filter tests opt in explicitly."""
    monkeypatch.setattr(workday, "WORKDAY_COUNTRY", "")
    monkeypatch.setattr(workday, "WORKDAY_PAGE_DELAY_S", 0)

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

    def _spy(host: str, tenant: str, site: str, search_text: str, **_kw: Any) -> dict:
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

    def _spy(host: str, tenant: str, site: str, search_text: str, **_kw: Any) -> dict:
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


# ---------- country filter + paging ----------

_SALESFORCE_STYLE_FACETS: list[dict[str, Any]] = [
    {"facetParameter": "CF_Country_Extended", "descriptor": "Country",
     "values": [{"descriptor": "United States", "id": "us"},
                {"descriptor": "India", "id": "in-country"}]},
    {"facetParameter": "locationMainGroup", "values": [
        {"facetParameter": "locations", "values": [
            {"descriptor": "India - Bangalore", "id": "blr"},
            {"descriptor": "Indiana - Remote", "id": "indiana"},
        ]},
    ]},
]


def test_exact_country_facet_is_preferred():
    assert workday.country_facets(_SALESFORCE_STYLE_FACETS, "India") == {
        "CF_Country_Extended": ["in-country"],
    }


def test_falls_back_to_locations_under_the_country_never_indiana():
    facets = [_SALESFORCE_STYLE_FACETS[1], {
        "facetParameter": "locations", "descriptor": "Locations",
        "values": [{"descriptor": "Bengaluru, India", "id": "blr2"},
                   {"descriptor": "Indianapolis, IN", "id": "indy"},
                   {"descriptor": "Pune, India ", "id": "pune"}],
    }]
    assert workday.country_facets(facets, "India") == {"locations": ["blr", "blr2", "pune"]}


def test_no_country_facet_means_no_filter():
    facets = [{"facetParameter": "locations", "values": [{"descriptor": "Austin, TX", "id": "a"}]}]
    assert workday.country_facets(facets, "India") == {}


def _page(n: int, total: int) -> dict[str, Any]:
    return {"total": total, "jobPostings": [
        {"title": f"Software Engineer {n}-{i}", "locationsText": "India - Bangalore",
         "externalPath": f"/job/{n}-{i}"} for i in range(2)
    ]}


@pytest.fixture
def filtered(monkeypatch):
    monkeypatch.setattr(workday, "WORKDAY_COUNTRY", "India")
    monkeypatch.setattr(workday, "WORKDAY_SEARCH_TEXT", "software engineer")
    monkeypatch.setattr(workday, "WORKDAY_MIN_INTERVAL_S", 0)
    monkeypatch.setattr(workday, "_last_fetch", {})


def test_filtered_discover_applies_country_and_pages(monkeypatch, filtered):
    monkeypatch.setattr(workday, "WORKDAY_MAX_PAGES", 5)
    calls: list[dict[str, Any]] = []

    def _spy(host: str, tenant: str, site: str, search_text: str, **kw: Any) -> dict:
        calls.append({"search": search_text, **kw})
        if kw.get("limit") == 1:  # facets probe
            return {"total": 45, "facets": _SALESFORCE_STYLE_FACETS, "jobPostings": []}
        return _page(kw.get("offset", 0) // 20, total=45)

    monkeypatch.setattr(workday, "_fetch", _spy)
    result = workday.WorkdaySource().discover(keyword=_KEYWORD, dry_run=True)

    assert calls[0]["limit"] == 1 and calls[0]["search"] == "software engineer"
    pages = calls[1:]
    assert [c["offset"] for c in pages] == [0, 20, 40]  # stops once offset >= total (45)
    assert all(c["applied_facets"] == {"CF_Country_Extended": ["in-country"]} for c in pages)
    assert result["found"] == 6


def test_filtered_discover_respects_max_pages(monkeypatch, filtered):
    monkeypatch.setattr(workday, "WORKDAY_MAX_PAGES", 2)
    offsets: list[int] = []

    def _spy(host: str, tenant: str, site: str, search_text: str, **kw: Any) -> dict:
        if kw.get("limit") == 1:
            return {"facets": _SALESFORCE_STYLE_FACETS}
        offsets.append(kw.get("offset", 0))
        return _page(0, total=500)

    monkeypatch.setattr(workday, "_fetch", _spy)
    workday.WorkdaySource().discover(keyword=_KEYWORD, dry_run=True)
    assert offsets == [0, 20]


def test_board_without_country_fetches_nothing_more(monkeypatch, filtered):
    calls: list[int] = []

    def _spy(host: str, tenant: str, site: str, search_text: str, **kw: Any) -> dict:
        calls.append(kw.get("limit", 20))
        return {"facets": [], "jobPostings": []}

    monkeypatch.setattr(workday, "_fetch", _spy)
    assert workday.WorkdaySource().discover(keyword=_KEYWORD, dry_run=True)["found"] == 0
    assert calls == [1]  # only the facets probe


def test_rate_limit_mid_paging_keeps_earlier_pages(monkeypatch, filtered):
    monkeypatch.setattr(workday, "WORKDAY_MAX_PAGES", 5)

    def _spy(host: str, tenant: str, site: str, search_text: str, **kw: Any) -> dict:
        if kw.get("limit") == 1:
            return {"facets": _SALESFORCE_STYLE_FACETS}
        if kw.get("offset", 0) >= 20:
            req = httpx.Request("POST", "https://x")
            raise httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, request=req))
        return _page(0, total=100)

    monkeypatch.setattr(workday, "_fetch", _spy)
    assert workday.WorkdaySource().discover(keyword=_KEYWORD, dry_run=True)["found"] == 2
