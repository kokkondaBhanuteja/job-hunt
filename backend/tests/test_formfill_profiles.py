"""Form-profile loading + validation for the ATS autofill engine."""
from __future__ import annotations

from job_hunt.apply.formfill_profiles import load_profile, validate_profile


def test_load_greenhouse_profile_is_valid():
    p = load_profile("greenhouse")
    assert p is not None and p["ats"] == "greenhouse"
    assert validate_profile(p) is None


def test_load_lever_profile_is_valid():
    p = load_profile("lever")
    assert p is not None and validate_profile(p) is None


def test_load_unknown_ats_returns_none():
    assert load_profile("workday") is None


def test_validate_rejects_missing_fields_key():
    assert validate_profile({"ats": "x", "match": {}}) is not None
