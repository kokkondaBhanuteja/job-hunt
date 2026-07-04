"""Tests for Groq provider: registry wiring, key rotation, fallback, and cost.

All tests are hermetic — network is stubbed via monkeypatch; no real API calls are made.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from job_hunt.llm import client, registry
from job_hunt.llm.base import LLMError
from job_hunt.llm.providers.openai_compat import OpenAICompatProvider

# ---------------------------------------------------------------------------
# Fake HTTP primitives
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal stand-in for httpx.Response that supports raise_for_status() and json()."""

    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict[str, Any]:
        """Return the stubbed JSON body."""
        return self._body

    def raise_for_status(self) -> None:
        """Raise HTTPStatusError for 4xx/5xx status codes, matching real httpx behaviour."""
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request(
                    "POST", "https://api.groq.com/openai/v1/chat/completions"
                ),
                response=self,  # type: ignore[arg-type]
            )


def _ok_response(content: str = "hello from groq") -> _FakeResponse:
    """Return a fake 200 response with a valid chat-completion body."""
    return _FakeResponse(
        200,
        {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

def test_provider_for_groq_returns_openai_compat_at_groq_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """_provider_for('groq') builds an OpenAICompatProvider pointed at api.groq.com."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testkey")
    provider = registry._provider_for("groq")
    assert isinstance(provider, OpenAICompatProvider)
    assert "groq.com" in provider.base_url


def test_provider_for_groq_reads_api_keys_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """GROQ_API_KEYS (comma-separated) is parsed into a list of keys."""
    monkeypatch.setenv("GROQ_API_KEYS", "gsk_a, gsk_b , gsk_c")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    provider = registry._provider_for("groq")
    assert isinstance(provider, OpenAICompatProvider)
    assert len(provider._keys) == 3


# ---------------------------------------------------------------------------
# Key rotation
# ---------------------------------------------------------------------------

def test_rotation_succeeds_on_second_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """First key gets HTTP 429; provider rotates to second key and returns content."""
    call_count = 0

    def _fake_post(url: str, *, json: Any, headers: dict[str, str], timeout: float) -> _FakeResponse:
        nonlocal call_count
        call_count += 1
        return _FakeResponse(429) if call_count == 1 else _ok_response("rotated")

    monkeypatch.setattr("job_hunt.llm.providers.openai_compat.httpx.post", _fake_post)
    provider = OpenAICompatProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_keys=["key_bad", "key_good"],
    )
    result = provider.chat(
        [{"role": "user", "content": "hi"}], model="llama-3.3-70b-versatile"
    )
    assert result.text == "rotated"
    assert call_count == 2  # confirmed rotation happened


def test_rotation_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 401 (invalid key) also triggers rotation to the next key."""
    call_count = 0

    def _fake_post(url: str, *, json: Any, headers: dict[str, str], timeout: float) -> _FakeResponse:
        nonlocal call_count
        call_count += 1
        return _FakeResponse(401) if call_count == 1 else _ok_response("ok-after-401")

    monkeypatch.setattr("job_hunt.llm.providers.openai_compat.httpx.post", _fake_post)
    provider = OpenAICompatProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_keys=["bad_key", "good_key"],
    )
    result = provider.chat([{"role": "user", "content": "hi"}], model="llama-3.1-8b-instant")
    assert result.text == "ok-after-401"


def test_all_keys_exhausted_raises_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    """All keys return 429 → provider raises LLMError(retryable=True)."""
    monkeypatch.setattr(
        "job_hunt.llm.providers.openai_compat.httpx.post",
        lambda *a, **kw: _FakeResponse(429),
    )
    provider = OpenAICompatProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_keys=["key1", "key2"],
    )
    with pytest.raises(LLMError) as exc_info:
        provider.chat([{"role": "user", "content": "hi"}], model="llama-3.3-70b-versatile")
    assert exc_info.value.retryable is True
    assert "exhausted" in str(exc_info.value).lower()


def test_permanent_error_400_raises_not_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 400 (bad request) is a permanent error — raises LLMError(retryable=False)."""
    monkeypatch.setattr(
        "job_hunt.llm.providers.openai_compat.httpx.post",
        lambda *a, **kw: _FakeResponse(400),
    )
    provider = OpenAICompatProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_keys=["key1"],
    )
    with pytest.raises(LLMError) as exc_info:
        provider.chat([{"role": "user", "content": "hi"}], model="llama-3.3-70b-versatile")
    assert exc_info.value.retryable is False


def test_no_api_key_raises_not_retryable() -> None:
    """Provider with no keys raises LLMError(retryable=False) without making any HTTP calls."""
    provider = OpenAICompatProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_keys=[],
    )
    with pytest.raises(LLMError) as exc_info:
        provider.chat([{"role": "user", "content": "hi"}], model="llama-3.3-70b-versatile")
    assert exc_info.value.retryable is False


# ---------------------------------------------------------------------------
# Fallback path: groq exhausted → client falls back to stub
# ---------------------------------------------------------------------------

def test_fallback_to_stub_when_groq_exhausted(
    tmp_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Primary Groq exhausts all keys (429) → client.chat falls back to stub provider."""
    monkeypatch.setattr(
        "job_hunt.llm.providers.openai_compat.httpx.post",
        lambda *a, **kw: _FakeResponse(429),
    )
    groq_provider = OpenAICompatProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_keys=["only_key"],
    )

    from job_hunt.llm.providers.stub import StubProvider

    stub = StubProvider()
    monkeypatch.setattr(
        client.registry, "resolve", lambda task: (groq_provider, "llama-3.3-70b-versatile")
    )
    monkeypatch.setattr(
        client.registry, "resolve_fallback", lambda task: (stub, "stub")
    )

    out = client.chat("test fallback", task="drafting")
    assert out == "stub response"


# ---------------------------------------------------------------------------
# Cost: Groq free models report $0 with no warning
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
])
def test_cost_groq_free_model_is_zero_no_warning(
    model: str, caplog: pytest.LogCaptureFixture
) -> None:
    """All Groq free models return 0.0 cost and emit no 'no price' log warning."""
    with caplog.at_level(logging.WARNING, logger="job_hunt.llm.registry"):
        c = registry.cost(model, 1000, 1000)
    assert c == 0.0
    assert "no price" not in caplog.text
