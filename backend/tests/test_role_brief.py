"""Tests for the interview-prep brief service (no real LLM calls)."""
from __future__ import annotations

from job_hunt.services import brief


def _seed_job(db):
    return db.insert_job_if_new(
        dedup_hash="brief-hash",
        source="naukri",
        source_job_id=None,
        title="Backend Engineer",
        company="Acme",
        location="bangalore",
        description="NestJS + Postgres",
        apply_url="https://example.com/1",
        posted_date=None,
    )


_STUB_RESULT = {
    "summary": "Backend role using NestJS",
    "key_skills": ["Node"],
    "interview_topics": ["system design"],
    "questions_to_ask": ["team size?"],
    "fit_notes": "good",
}


def test_brief_for_job_returns_stub_result(tmp_db, monkeypatch):
    jid = _seed_job(tmp_db)
    captured: dict = {}

    def _stub(prompt, *, schema, task, system, prompt_name, prompt_version):
        captured["prompt"] = prompt
        return dict(_STUB_RESULT)

    monkeypatch.setattr(brief, "chat_json", _stub)

    result = brief.brief_for_job(jid)

    assert result["summary"] == _STUB_RESULT["summary"]
    assert result["key_skills"] == ["Node"]
    assert result["interview_topics"] == ["system design"]
    assert result["questions_to_ask"] == ["team size?"]
    assert result["fit_notes"] == "good"


def test_brief_for_job_prompt_contains_jd_and_company(tmp_db, monkeypatch):
    jid = _seed_job(tmp_db)
    captured: dict = {}

    def _stub(prompt, *, schema, task, system, prompt_name, prompt_version):
        captured["prompt"] = prompt
        return dict(_STUB_RESULT)

    monkeypatch.setattr(brief, "chat_json", _stub)
    brief.brief_for_job(jid)

    # The JD text and company name must appear in the constructed prompt.
    assert "NestJS + Postgres" in captured["prompt"]
    assert "Acme" in captured["prompt"]


def test_brief_for_job_missing_id_returns_error(tmp_db, monkeypatch):
    monkeypatch.setattr(brief, "chat_json", lambda *a, **k: dict(_STUB_RESULT))

    result = brief.brief_for_job(99999)

    assert "error" in result
    assert "99999" in result["error"]
