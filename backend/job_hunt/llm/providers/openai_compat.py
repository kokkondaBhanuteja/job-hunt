"""OpenAI-compatible provider — works against OpenAI, Gemini's openai-compat endpoint,
and Groq (set base_url + api key(s) via env). Used when a task is routed to the cloud.

JSON output is requested via `response_format={"type":"json_object"}` (broadly
supported); the client still validates/repairs, so `supports_schema = True` is a
best-effort hint rather than a hard guarantee.

Key rotation: pass `api_keys` (a list) to rotate across multiple keys on 429/401/403.
The single `api_key` parameter is kept for backwards compatibility (openai/gemini).
When all keys are exhausted the provider raises a retryable `LLMError` so the client
falls back to the configured fallback provider (e.g. local Ollama).
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.llm.base import ChatResult, LLMError
from job_hunt.logging_config import get_logger

logger = get_logger(__name__)

# HTTP status codes that mean "this key is rate-limited or invalid; try the next one".
_ROTATE_ON: frozenset[int] = frozenset({429, 401, 403})
# HTTP status codes that mean the request itself is bad — rotating keys won't help.
_PERMANENT_CODES: frozenset[int] = frozenset({400, 404, 422})


class OpenAICompatProvider:
    """OpenAI-compatible chat provider with optional multi-key rotation."""

    supports_schema = True

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str | None = None,
        api_keys: list[str] | None = None,
    ) -> None:
        """Initialise provider; normalise api_key / api_keys to an internal list."""
        self.name = name
        self.base_url = base_url.rstrip("/")
        # Normalise: api_keys takes precedence; fall back to single api_key.
        self._keys: list[str] = list(api_keys) if api_keys else ([api_key] if api_key else [])
        # Back-compat: expose api_key for callers that read it directly.
        self.api_key = self._keys[0] if self._keys else None

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        timeout_s: float = 120.0,
    ) -> ChatResult:
        """Send a chat completion request, rotating keys on 429/401/403."""
        if not self._keys:
            raise LLMError(
                f"{self.name}: no API key set (configure the provider's API key env var).",
                retryable=False,
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        for idx, key in enumerate(self._keys):
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=timeout_s,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in _ROTATE_ON:
                    # Key is rate-limited or invalid — rotate to the next one.
                    remaining = len(self._keys) - idx - 1
                    logger.debug(
                        "%s: key index %d got HTTP %d; %d key(s) remaining",
                        self.name, idx, status, remaining,
                    )
                    continue
                if status in _PERMANENT_CODES:
                    # Bad request — rotating won't help.
                    raise LLMError(
                        f"{self.name} call failed ({model}): {exc}", retryable=False
                    ) from exc
                # Other 4xx/5xx — treat as retryable by the outer client.
                raise LLMError(
                    f"{self.name} call failed ({model}): {exc}", retryable=True
                ) from exc
            except httpx.HTTPError as exc:
                # Timeout / connection error — let the outer client retry/fall back.
                raise LLMError(f"{self.name} call failed ({model}): {exc}") from exc

            body = resp.json()
            usage = body.get("usage") or {}
            return ChatResult(
                text=body["choices"][0]["message"]["content"],
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )

        # All keys were exhausted (all returned 429/401/403).
        raise LLMError(
            f"{self.name}: all API keys exhausted or rate-limited (tried {len(self._keys)})",
            retryable=True,
        )
