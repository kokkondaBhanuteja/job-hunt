"""A3: chat_json retries + repairs on invalid model output instead of hard-failing once."""
from __future__ import annotations

import pytest

from job_hunt.llm import client
from job_hunt.llm.base import ChatResult, LLMError


class _Provider:
    """Returns `outputs` in order across calls (simulates a flaky model)."""

    name = "flaky"
    supports_schema = False

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def chat(self, messages, *, model, json_schema, temperature, timeout_s):
        out = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
        return ChatResult(text=out, prompt_tokens=1, completion_tokens=1)


SCHEMA = {"type": "object", "required": ["fit_score"], "properties": {"fit_score": {"type": "integer"}}}


def test_chat_json_repairs_after_invalid_output(tmp_db, monkeypatch):
    provider = _Provider(["not json at all", '{"fit_score": 88}'])
    monkeypatch.setattr(client.registry, "resolve", lambda task: (provider, "m"))
    monkeypatch.setattr(client.registry, "resolve_fallback", lambda task: None)
    monkeypatch.setattr(client, "_MAX_ATTEMPTS", 2)

    out = client.chat_json("score it", schema=SCHEMA)
    assert out["fit_score"] == 88
    assert provider.calls == 2  # first invalid → repaired on the retry


def test_chat_json_raises_after_exhausting_attempts(tmp_db, monkeypatch):
    provider = _Provider(["garbage", "still garbage"])
    monkeypatch.setattr(client.registry, "resolve", lambda task: (provider, "m"))
    monkeypatch.setattr(client.registry, "resolve_fallback", lambda task: None)
    monkeypatch.setattr(client, "_MAX_ATTEMPTS", 2)

    with pytest.raises(LLMError):
        client.chat_json("score it", schema=SCHEMA)
