"""Local Ollama provider — the $0 default. Wraps `ollama serve`'s /api/chat.

Ollama constrains output to a JSON schema via the `format` key, so
`supports_schema = True`.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from job_hunt.llm.base import ChatResult, LLMError

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S", "120"))


class OllamaProvider:
    name = "ollama"
    supports_schema = True

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_schema is not None:
            payload["format"] = json_schema  # Ollama structured-output

        try:
            resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout_s)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama call failed ({model}): {exc}") from exc

        body = resp.json()
        return ChatResult(
            text=body["message"]["content"],
            prompt_tokens=body.get("prompt_eval_count"),
            completion_tokens=body.get("eval_count"),
        )


# ---- liveness helpers (used by `hunt selfcheck`) ----


def is_alive() -> bool:
    """Quick liveness check for `ollama serve`."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/version", timeout=2.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def installed_models() -> list[str]:
    """Names of models currently pulled in Ollama."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except httpx.HTTPError:
        return []
