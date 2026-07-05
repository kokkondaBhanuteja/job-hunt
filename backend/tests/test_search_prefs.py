"""Tests for the search_prefs service (set/get preferences + profile creation)."""
from __future__ import annotations

from job_hunt.services import search_prefs
from job_hunt.storage import repo

_STUB_TWO = {
    "profiles": [
        {"name": "BE blr", "keywords": "nestjs backend", "location": "bangalore", "pages": 1},
        {"keywords": "nestjs backend", "location": "remote"},
    ]
}


def test_set_search_prefs_creates_profiles(tmp_db, monkeypatch):
    """Parsed profiles are written and {ok, profiles_created} is returned."""
    monkeypatch.setattr(search_prefs, "chat_json", lambda *a, **k: _STUB_TWO)
    result = search_prefs.set_search_prefs("# I want backend NestJS roles in Bangalore or remote")
    assert result == {"ok": True, "profiles_created": 2}
    profiles = repo.list_search_profiles()
    assert len(profiles) == 2
    locations = {p["location"] for p in profiles}
    assert locations == {"bangalore", "remote"}
    keywords = {p["keywords"] for p in profiles}
    assert keywords == {"nestjs backend"}


def test_set_search_prefs_roundtrips_content(tmp_db, monkeypatch):
    """Stored markdown is returned verbatim by get_search_prefs."""
    monkeypatch.setattr(search_prefs, "chat_json", lambda *a, **k: _STUB_TWO)
    md = "# I want backend NestJS roles in Bangalore or remote"
    search_prefs.set_search_prefs(md)
    assert search_prefs.get_search_prefs()["content"] == md


def test_set_search_prefs_empty_content(tmp_db):
    """Empty or whitespace-only content returns an error dict."""
    result = search_prefs.set_search_prefs("   ")
    assert "error" in result


def test_set_search_prefs_no_profiles_parsed(tmp_db, monkeypatch):
    """LLM returning no profiles yields an error dict."""
    monkeypatch.setattr(search_prefs, "chat_json", lambda *a, **k: {"profiles": []})
    result = search_prefs.set_search_prefs("some prefs text")
    assert "error" in result


def test_get_search_prefs_returns_nulls_if_unset(tmp_db):
    """get_search_prefs returns {content: None, updated_at: None} when nothing stored."""
    result = search_prefs.get_search_prefs()
    assert result["content"] is None
    assert result["updated_at"] is None
