"""Characterization tests for dedup / URL helpers in job_hunt/sources/naukri.py."""
from __future__ import annotations

from job_hunt.sources.naukri import (
    _normalize_title,
    _slug,
    build_search_url,
    dedup_hash,
)


def test_normalize_title_strips_seniority():
    assert _normalize_title("Senior Backend Engineer") == "backend engineer"
    assert _normalize_title("Jr. Backend Engineer") == "backend engineer"
    assert _normalize_title("Lead Backend Engineer") == "backend engineer"


def test_dedup_hash_is_stable_and_seniority_insensitive():
    a = dedup_hash("Acme Corp", "Senior Backend Engineer")
    b = dedup_hash("Acme Corp", "Backend Engineer")
    # Same company + normalized title (+ default location) → identical hash.
    assert a == b
    # Different company → different hash.
    assert dedup_hash("Other Corp", "Backend Engineer") != a


def test_dedup_hash_includes_location():
    blr = dedup_hash("Acme Corp", "Backend Engineer", "Bangalore")
    hyd = dedup_hash("Acme Corp", "Backend Engineer", "Hyderabad")
    # Same role in different cities is NOT a duplicate.
    assert blr != hyd
    # Same everything → identical.
    assert blr == dedup_hash("Acme Corp", "Backend Engineer", "Bangalore")


def test_slug():
    assert _slug("NestJS Backend") == "nestjs-backend"
    assert _slug("  Hyderabad  ") == "hyderabad"


def test_build_search_url():
    assert build_search_url("nestjs backend", "bangalore") == (
        "https://www.naukri.com/nestjs-backend-jobs-in-bangalore"
    )
    assert build_search_url("nestjs backend", "bangalore", page=3) == (
        "https://www.naukri.com/nestjs-backend-jobs-in-bangalore-3"
    )
