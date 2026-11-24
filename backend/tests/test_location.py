"""Tests for the India / open-remote location gate (sources/location.py) and its use on save."""
from __future__ import annotations

import pytest

from job_hunt.plugins import _persist
from job_hunt.sources import location


@pytest.fixture(autouse=True)
def _filter_on(monkeypatch):
    """conftest turns the filter off for plugin tests; these cases test the filter itself."""
    monkeypatch.setattr(location, "JOB_LOCATION_FILTER", "india-remote")


@pytest.mark.parametrize("loc", [
    "Bengaluru, India", "India - Bangalore", "Hyderabad", "Gurugram, Haryana", "Pune, MH",
    "Remote, India", "Remote - India", "India (Remote)", "San Francisco, CA; Bengaluru, India",
    "Remote", "remote", "Anywhere", "Worldwide", "Remote (Worldwide)", "100% Remote",
    "Remote - APAC", "Remote, Asia-Pacific", "Global", "Anywhere in the World",
    # real We Work Remotely regions, stored as "Remote - <region>"
    "Remote - Anywhere in the World", "Remote - Asia Only",
])
def test_keeps_india_and_open_remote(loc):
    assert location.is_india_or_open_remote(loc) is True


@pytest.mark.parametrize("loc", [
    # real values seen in the first Neon run
    "US Only", "Canada Only", "München", "Arlington", "Europe", "EMEA", "UK Only",
    # restricted remote and on-site abroad
    "Remote - US", "Remote (USA)", "Remote, United States", "Remote - EMEA", "Remote, Europe",
    "Remote - Canada", "San Francisco, CA", "London, UK", "Indianapolis, IN", "Indiana - Remote",
    # real We Work Remotely regions
    "Remote - USA Only", "Remote - Europe Only", "Remote - North America Only",
    "Remote - Canada Only",
])
def test_drops_jobs_restricted_outside_india(loc):
    assert location.is_india_or_open_remote(loc) is False


def test_india_in_title_counts():
    assert location.is_india_or_open_remote("Remote - EMEA", "Backend Engineer (India)") is True


def test_unknown_location_is_kept_for_scoring():
    assert location.is_india_or_open_remote("") is True
    assert location.is_india_or_open_remote(None) is True


def test_filter_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(location, "JOB_LOCATION_FILTER", "off")
    assert location.is_india_or_open_remote("US Only") is True


def _save(loc: str) -> bool:
    return _persist.persist_full_jd_job(
        source="remoteok", source_job_id=f"id-{loc}", title="Backend Engineer",
        company="Acme", location=loc, full_jd="Build APIs.", apply_url="https://x/1",
    )


def test_persist_skips_jobs_outside_filter(tmp_db):
    assert _save("US Only") is False
    assert _save("Bengaluru, India") is True
    stored = [r["location"] for r in tmp_db.raw_select("SELECT location FROM jobs")]
    assert stored == ["Bengaluru, India"]
