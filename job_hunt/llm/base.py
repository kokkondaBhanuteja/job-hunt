"""Provider-agnostic LLM contract.

Every concrete provider (Ollama, OpenAI-compat, stub) implements `LLMProvider`.
The registry resolves a *task* (scoring / drafting / tailoring) to a provider +
model from env, so the toolkit runs $0-local by default or against an API key —
configurable per task, without touching call sites.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class LLMError(RuntimeError):
    """Raised when a provider is unreachable or returns an error.

    `retryable=False` marks a permanent failure (bad key, malformed request) so the
    caller stops retrying the same provider instead of burning attempts.
    """

    def __init__(self, *args: object, retryable: bool = True) -> None:
        super().__init__(*args)
        self.retryable = retryable


@dataclass
class ChatResult:
    """One chat turn's result + usage (for the llm_calls log / cost dashboard)."""

    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """A chat backend. `name` labels the log; `supports_schema` says whether the
    provider can constrain output to a JSON schema natively (else we prompt-and-parse).
    """

    name: str
    supports_schema: bool

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        timeout_s: float = 120.0,
    ) -> ChatResult: ...
