"""Back-compat facade for the LLM layer.

Historically every LLM call imported from `job_hunt.llm.ollama`. That still works,
but the implementation now lives behind a provider registry (see `llm/registry.py`)
so any task can be pointed at a local model OR an API key via env. These re-exports
keep existing call sites (scoring, resume parsing, CLI) untouched.
"""
from __future__ import annotations

from job_hunt.llm.base import LLMError
from job_hunt.llm.client import chat, chat_json
from job_hunt.llm.providers.ollama import (
    DEFAULT_TIMEOUT_S,
    OLLAMA_URL,
    installed_models,
    is_alive,
)
from job_hunt.llm.registry import DRAFTING_MODEL, SCORING_MODEL

# Legacy alias — some call sites caught `OllamaError`.
OllamaError = LLMError

__all__ = [
    "chat",
    "chat_json",
    "is_alive",
    "installed_models",
    "OLLAMA_URL",
    "DEFAULT_TIMEOUT_S",
    "SCORING_MODEL",
    "DRAFTING_MODEL",
    "OllamaError",
    "LLMError",
]
