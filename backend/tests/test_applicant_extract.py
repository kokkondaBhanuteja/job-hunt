"""Tests for extract_applicant — LLM-based résumé-to-profile extraction (read-only)."""
from __future__ import annotations

import job_hunt.services.applicant as applicant_mod
from job_hunt.services.applicant import extract_applicant, get_applicant

_FAKE_RESULT = {
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@x.com",
    "github_url": "github.com/jane",
    "years_experience": "3",
}

_RESUME_TEXT = "Jane Doe\njane@x.com\ngithub.com/jane\n3 years backend experience"


def test_extract_returns_llm_fields(tmp_db, monkeypatch):
    """Extract passes résumé to LLM and returns only recognized applicant extract fields."""
    monkeypatch.setattr(applicant_mod, "chat_json", lambda *a, **k: _FAKE_RESULT)
    result = extract_applicant(_RESUME_TEXT)
    assert result["first_name"] == "Jane"
    assert result["last_name"] == "Doe"
    assert result["email"] == "jane@x.com"
    assert result["github_url"] == "github.com/jane"
    assert result["years_experience"] == "3"


def test_extract_filters_to_known_fields(tmp_db, monkeypatch):
    """Extract strips any extra keys the LLM might return beyond the schema fields."""
    extra = {**_FAKE_RESULT, "hallucinated_key": "oops", "work_authorization": "citizen"}
    monkeypatch.setattr(applicant_mod, "chat_json", lambda *a, **k: extra)
    result = extract_applicant(_RESUME_TEXT)
    assert "hallucinated_key" not in result
    assert "work_authorization" not in result


def test_extract_resume_text_reaches_prompt(tmp_db, monkeypatch):
    """The raw résumé content must appear in the prompt passed to the LLM."""
    captured: dict[str, str] = {}

    def fake_chat_json(prompt: str, **kw: object) -> dict[str, str]:
        captured["prompt"] = prompt
        captured["system"] = str(kw.get("system", ""))
        return _FAKE_RESULT

    monkeypatch.setattr(applicant_mod, "chat_json", fake_chat_json)
    extract_applicant(_RESUME_TEXT)
    assert _RESUME_TEXT in captured["prompt"]


def test_extract_system_prompt_has_injection_hardening(tmp_db, monkeypatch):
    """The system prompt must instruct the LLM to treat the résumé as data only."""
    captured: dict[str, str] = {}

    def fake_chat_json(prompt: str, **kw: object) -> dict[str, str]:
        captured["system"] = str(kw.get("system", ""))
        return _FAKE_RESULT

    monkeypatch.setattr(applicant_mod, "chat_json", fake_chat_json)
    extract_applicant(_RESUME_TEXT)
    system_lower = captured["system"].lower()
    assert "data" in system_lower or "never follow" in system_lower


def test_extract_empty_content_returns_error(tmp_db, monkeypatch):
    """Empty or whitespace-only content must return {error: ...} without calling the LLM."""
    called = []
    monkeypatch.setattr(applicant_mod, "chat_json", lambda *a, **k: called.append(1) or {})
    result = extract_applicant("")
    assert "error" in result
    assert not called


def test_extract_whitespace_only_returns_error(tmp_db, monkeypatch):
    """Whitespace-only content must also return {error: ...}."""
    monkeypatch.setattr(applicant_mod, "chat_json", lambda *a, **k: {})
    result = extract_applicant("   \n  ")
    assert "error" in result


def test_extract_does_not_save_to_db(tmp_db, monkeypatch):
    """extract_applicant must NOT write to applicant_profile — the caller reviews then saves."""
    monkeypatch.setattr(applicant_mod, "chat_json", lambda *a, **k: _FAKE_RESULT)
    extract_applicant(_RESUME_TEXT)
    profile = get_applicant()
    assert profile["first_name"] is None
    assert profile["email"] is None
