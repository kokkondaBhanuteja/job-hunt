"""OpenAI-compatible provider — works against OpenAI and Gemini's openai-compat
endpoint (set base_url + api key via env). Used when a task is routed to the cloud.

JSON output is requested via `response_format={"type":"json_object"}` (broadly
supported); the client still validates/repairs, so `supports_schema = True` is a
best-effort hint rather than a hard guarantee.
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.llm.base import ChatResult, LLMError


class OpenAICompatProvider:
    supports_schema = True

    def __init__(self, *, name: str, base_url: str, api_key: str | None):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        timeout_s: float = 120.0,
    ) -> ChatResult:
        if not self.api_key:
            raise LLMError(
                f"{self.name}: no API key set (configure the provider's API key env var)."
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=timeout_s,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:  # 4xx auth/bad-request = permanent, don't retry
            permanent = exc.response.status_code in (400, 401, 403, 404, 422)
            raise LLMError(
                f"{self.name} call failed ({model}): {exc}", retryable=not permanent
            ) from exc
        except httpx.HTTPError as exc:  # timeout / connection = transient, retry
            raise LLMError(f"{self.name} call failed ({model}): {exc}") from exc

        body = resp.json()
        usage = body.get("usage") or {}
        return ChatResult(
            text=body["choices"][0]["message"]["content"],
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
