"""E: prompt versioning is now real — each LLM call records which versioned Prompt produced
it (prompt_name/prompt_version on llm_calls), instead of the field being dead metadata."""
from __future__ import annotations

from job_hunt.llm import client
from job_hunt.llm.base import ChatResult
from job_hunt.llm.prompts import SCORING
from job_hunt.scoring import match


class _Provider:
    name = "stub"
    supports_schema = False

    def chat(self, messages, *, model, json_schema, temperature, timeout_s):
        return ChatResult(text='{"fit_score": 80, "confidence": 70, "reasoning": "ok"}',
                          prompt_tokens=1, completion_tokens=1)


def test_llm_call_records_prompt_identity(tmp_db, monkeypatch):
    monkeypatch.setattr(client.registry, "resolve", lambda task: (_Provider(), "m"))
    monkeypatch.setattr(client.registry, "resolve_fallback", lambda task: None)

    match.score_one({"headline": "BE"}, {"title": "BE", "company": "Acme", "location": "blr",
                                         "source": "naukri"}, "JD text")

    with tmp_db.connect() as conn:
        row = conn.execute(
            "SELECT prompt_name, prompt_version FROM llm_calls ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["prompt_name"] == SCORING.name
    assert row["prompt_version"] == SCORING.version
