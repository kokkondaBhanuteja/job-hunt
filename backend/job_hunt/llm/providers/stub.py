"""Deterministic stub provider — no network. Used for offline `selfcheck` and tests.

When a JSON schema is requested, it synthesizes a minimal object satisfying the
schema's `required` properties, so structured-output call sites get valid data.
"""
from __future__ import annotations

from typing import Any

from job_hunt.llm.base import ChatResult


def _stub_value(prop_schema: dict[str, Any]) -> Any:
    t = prop_schema.get("type")
    if t == "integer" or t == "number":
        lo = prop_schema.get("minimum", 0)
        hi = prop_schema.get("maximum", lo)
        return lo if hi is None else (lo + hi) // 2 if t == "integer" else lo
    if t == "array":
        return []
    if t == "object":
        return _stub_object(prop_schema)
    if t == "boolean":
        return False
    return "stub"


def _stub_object(schema: dict[str, Any]) -> dict[str, Any]:
    props = schema.get("properties", {})
    required = schema.get("required", list(props.keys()))
    return {key: _stub_value(props.get(key, {})) for key in required}


class StubProvider:
    name = "stub"
    supports_schema = True

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        timeout_s: float = 120.0,
    ) -> ChatResult:
        if json_schema is not None:
            import json

            return ChatResult(text=json.dumps(_stub_object(json_schema)),
                              prompt_tokens=0, completion_tokens=0)
        return ChatResult(text="stub response", prompt_tokens=0, completion_tokens=0)
