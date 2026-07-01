"""Tests for the pluggable LLM layer: registry resolution, stub provider,
call logging, JSON fallback parsing, and confidence persistence."""
from __future__ import annotations

import pytest

from job_hunt.llm import client, registry
from job_hunt.llm.base import ChatResult, LLMError
from job_hunt.llm.providers.ollama import OllamaProvider
from job_hunt.llm.providers.stub import StubProvider


class _FlakyProvider:
    name = "flaky"
    supports_schema = True

    def __init__(self, fail_times: int):
        self.calls = 0
        self.fail_times = fail_times

    def chat(self, messages, *, model, json_schema=None, temperature=0.2, timeout_s=120.0):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise LLMError("transient")
        return ChatResult(text="ok after retry", prompt_tokens=1, completion_tokens=1)


def test_resolve_defaults_to_local_ollama(monkeypatch):
    monkeypatch.delenv("LLM_SCORING_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_SCORING_MODEL", raising=False)
    provider, model = registry.resolve("scoring")
    assert isinstance(provider, OllamaProvider)
    assert model == "qwen2.5:7b"


def test_resolve_honors_env_provider_and_model(monkeypatch):
    monkeypatch.setenv("LLM_DRAFTING_PROVIDER", "stub")
    monkeypatch.setenv("LLM_DRAFTING_MODEL", "my-model")
    provider, model = registry.resolve("drafting")
    assert isinstance(provider, StubProvider)
    assert model == "my-model"


def test_resolve_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_SCORING_PROVIDER", "doesnotexist")
    with pytest.raises(LLMError):
        registry.resolve("scoring")


def test_chat_logs_every_call(tmp_db, monkeypatch):
    monkeypatch.setenv("LLM_SCORING_PROVIDER", "stub")
    out = client.chat("hello", task="scoring")
    assert out == "stub response"

    rows = [dict(r) for r in _all_llm_calls(tmp_db)]
    assert len(rows) == 1
    assert rows[0]["provider"] == "stub"
    assert rows[0]["ok"] == 1
    assert rows[0]["prompt"] == "hello"
    assert rows[0]["latency_ms"] is not None


def test_chat_json_returns_schema_satisfying_object(tmp_db, monkeypatch):
    monkeypatch.setenv("LLM_SCORING_PROVIDER", "stub")
    schema = {
        "type": "object",
        "required": ["fit_score", "reasoning"],
        "properties": {
            "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "reasoning": {"type": "string"},
        },
    }
    data = client.chat_json("score this", schema=schema, task="scoring")
    assert set(["fit_score", "reasoning"]).issubset(data)
    assert isinstance(data["fit_score"], int)


def test_parse_json_extracts_block_from_prose():
    schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
    out = client._parse_json('here is your answer: {"a": 5} thanks', schema)
    assert out == {"a": 5}


def test_parse_json_raises_on_garbage():
    schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
    with pytest.raises(LLMError):
        client._parse_json("no json here at all", schema)


def test_confidence_persists(tmp_db):
    job_id = tmp_db.insert_job_if_new(
        dedup_hash="c1", source="naukri", source_job_id=None, title="BE",
        company="Acme", location="blr", description="d", apply_url="u", posted_date=None,
    )
    vid = tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    tmp_db.write_score(job_id=job_id, variant_id=vid, fit_score=80, reasoning="r", confidence=42)

    with tmp_db.connect() as conn:
        row = conn.execute("SELECT confidence FROM scores WHERE job_id=?", (job_id,)).fetchone()
    assert row["confidence"] == 42


def test_chat_retries_transient_error(tmp_db, monkeypatch):
    flaky = _FlakyProvider(fail_times=1)  # fails once, then succeeds
    monkeypatch.setattr(client.registry, "resolve", lambda task: (flaky, "m"))
    monkeypatch.setattr(client.registry, "resolve_fallback", lambda task: None)

    out = client.chat("hi", task="scoring")
    assert out == "ok after retry"
    assert flaky.calls == 2

    rows = _all_llm_calls(tmp_db)
    assert [r["ok"] for r in rows] == [0, 1]  # one failed attempt, then success


def test_chat_falls_back_after_retries_exhausted(tmp_db, monkeypatch):
    primary = _FlakyProvider(fail_times=99)  # always fails
    monkeypatch.setattr(client.registry, "resolve", lambda task: (primary, "m"))
    monkeypatch.setattr(client.registry, "resolve_fallback", lambda task: (StubProvider(), "fb"))

    out = client.chat("hi", task="scoring")
    assert out == "stub response"
    # 2 exhausted primary attempts + 1 successful fallback.
    rows = _all_llm_calls(tmp_db)
    assert [r["ok"] for r in rows] == [0, 0, 1]


def _all_llm_calls(db):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM llm_calls ORDER BY id").fetchall()
