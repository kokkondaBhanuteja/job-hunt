"""Public LLM entrypoints: `chat()` and `chat_json()`.

These keep the v0 signatures so call sites (scoring, resume parsing, CLI) are
unchanged, but now route through the provider registry and log every call to the
`llm_calls` table (best-effort). `chat_json()` parses + validates, with a
prompt-and-parse fallback for providers that can't constrain output natively.
"""
from __future__ import annotations

import json
import os
import re
import time
from time import perf_counter
from typing import Any

from job_hunt.llm import registry
from job_hunt.llm.base import LLMError, LLMProvider
from job_hunt.logging_config import get_logger
from job_hunt.storage.repo import write_llm_call

logger = get_logger(__name__)

_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "2"))
_BACKOFF_BASE_S = float(os.getenv("LLM_BACKOFF_BASE_S", "0.5"))


def _build_messages(
    provider: LLMProvider, prompt: str, system: str | None, json_schema: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Assemble messages; if the provider can't constrain output, inline the schema."""
    native_schema = json_schema
    user_content = prompt
    if json_schema is not None and not provider.supports_schema:
        native_schema = None
        user_content = (
            f"{prompt}\n\nReturn ONLY valid JSON matching this schema:\n"
            f"{json.dumps(json_schema)}"
        )
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})
    return messages, native_schema


def _call(
    provider: LLMProvider, model: str, *, task: str, prompt: str, system: str | None,
    json_schema: dict[str, Any] | None, temperature: float, timeout_s: float | None,
) -> str:
    """One provider call. Logs to llm_calls (ok or error). Raises on failure."""
    messages, native_schema = _build_messages(provider, prompt, system, json_schema)
    t0 = perf_counter()
    try:
        result = provider.chat(
            messages, model=model, json_schema=native_schema,
            temperature=temperature, timeout_s=timeout_s or 120.0,
        )
    except Exception as exc:  # noqa: BLE001 — log the failure, then re-raise
        write_llm_call(
            task=task, provider=provider.name, model=model, prompt=prompt,
            response=None, latency_ms=int((perf_counter() - t0) * 1000),
            ok=False, error=str(exc),
        )
        raise

    write_llm_call(
        task=task, provider=provider.name, model=model, prompt=prompt,
        response=result.text, prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost=registry.cost(model, result.prompt_tokens, result.completion_tokens),
        latency_ms=int((perf_counter() - t0) * 1000), ok=True,
    )
    return result.text


def chat(
    prompt: str,
    *,
    task: str = "scoring",
    system: str | None = None,
    json_schema: dict[str, Any] | None = None,
    temperature: float = 0.2,
    timeout_s: float | None = None,
) -> str:
    """Run one chat turn for `task`, with bounded retries + an optional fallback provider.

    Retries the primary provider up to LLM_MAX_ATTEMPTS on transient LLMError, then (if
    configured via LLM_<TASK>_FALLBACK_PROVIDER) tries the fallback once. Every attempt
    is logged to llm_calls.
    """
    kwargs = dict(task=task, prompt=prompt, system=system, json_schema=json_schema,
                  temperature=temperature, timeout_s=timeout_s)

    provider, model = registry.resolve(task)
    last_exc: Exception | None = None
    attempts = max(1, _MAX_ATTEMPTS)
    for attempt in range(attempts):
        try:
            return _call(provider, model, **kwargs)
        except LLMError as exc:
            last_exc = exc
            if not exc.retryable:  # permanent (bad key / bad request) → don't burn attempts
                break
            if attempt + 1 < attempts:
                time.sleep(_BACKOFF_BASE_S * (2 ** attempt))  # exponential backoff

    fallback = registry.resolve_fallback(task)
    if fallback is not None:
        try:
            return _call(fallback[0], fallback[1], **kwargs)
        except LLMError as exc:
            last_exc = exc

    raise last_exc if last_exc is not None else LLMError("chat failed")


def chat_json(
    prompt: str,
    *,
    schema: dict[str, Any],
    task: str = "scoring",
    system: str | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Same as `chat()` but returns parsed JSON validated against `schema`.

    Invalid/malformed output — the most common local-model failure — is RETRIED with a
    repair turn ("your previous response was invalid: …"), up to LLM_MAX_ATTEMPTS. The
    previous behavior validated only once outside any retry and hard-failed.
    """
    attempts = max(1, _MAX_ATTEMPTS)
    last_exc: LLMError | None = None
    turn = prompt
    for attempt in range(attempts):
        raw = chat(turn, task=task, system=system, json_schema=schema, temperature=temperature)
        try:
            return _parse_json(raw, schema)
        except LLMError as exc:
            last_exc = exc
            logger.warning("chat_json invalid output (attempt %d/%d): %s",
                           attempt + 1, attempts, exc)
            turn = (
                f"{prompt}\n\nYour previous response was invalid ({exc}). "
                "Return ONLY valid JSON matching the required schema — no prose, no code fences."
            )
    raise last_exc if last_exc is not None else LLMError("chat_json failed")


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(raw: str, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract the first {...} block (some providers wrap JSON in prose).
        m = _JSON_BLOCK.search(raw)
        if not m:
            raise LLMError(f"Model returned non-JSON:\n{raw[:500]}") from None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned non-JSON:\n{raw[:500]}") from exc

    _validate(data, schema)
    return data


def _validate(data: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate against the schema when jsonschema is available; else check required keys."""
    try:
        import jsonschema  # transitively available via mcp

        jsonschema.validate(data, schema)
    except ImportError:
        missing = [k for k in schema.get("required", []) if k not in data]
        if missing:
            raise LLMError(f"JSON missing required keys: {missing}") from None
    except Exception as exc:  # jsonschema.ValidationError
        raise LLMError(f"JSON failed schema validation: {exc}") from exc
