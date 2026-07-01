"""Task → (provider, model) resolution from env. The single place that decides
whether a given task runs locally (Ollama) or against an API key.

Per task (e.g. 'scoring'), read:
    LLM_SCORING_PROVIDER   ollama | openai | gemini | stub   (default: ollama)
    LLM_SCORING_MODEL      provider-specific model name

Back-compat: if LLM_<TASK>_MODEL is unset, fall back to the legacy
OLLAMA_SCORING_MODEL / OLLAMA_DRAFTING_MODEL envs (default qwen2.5:7b).
"""
from __future__ import annotations

import os

from job_hunt.enums import LLMProvider as ProviderKind
from job_hunt.enums import LLMTask
from job_hunt.llm.base import LLMError, LLMProvider
from job_hunt.llm.providers.openai_compat import OpenAICompatProvider
from job_hunt.llm.providers.ollama import OllamaProvider
from job_hunt.llm.providers.stub import StubProvider

# Legacy defaults (preserve v0 behavior when LLM_* envs are unset).
SCORING_MODEL = os.getenv("OLLAMA_SCORING_MODEL", "qwen2.5:7b")
DRAFTING_MODEL = os.getenv("OLLAMA_DRAFTING_MODEL", "qwen2.5:7b")

_LEGACY_MODEL_DEFAULT = {LLMTask.SCORING: SCORING_MODEL, LLMTask.DRAFTING: DRAFTING_MODEL}

# Rough USD per 1K tokens (prompt, completion). 0 for local/stub. Extend as needed.
_COST_PER_1K: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "gemini-1.5-flash": (0.000075, 0.0003),
}


def _provider_for(kind: str) -> LLMProvider:
    try:
        pk = ProviderKind(kind.lower())
    except ValueError:
        allowed = "|".join(ProviderKind)
        raise LLMError(f"Unknown LLM provider '{kind}' (use {allowed})") from None

    if pk is ProviderKind.OLLAMA:
        return OllamaProvider()
    if pk is ProviderKind.STUB:
        return StubProvider()
    if pk is ProviderKind.OPENAI:
        return OpenAICompatProvider(
            name=ProviderKind.OPENAI,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    # pk is ProviderKind.GEMINI
    return OpenAICompatProvider(
        name=ProviderKind.GEMINI,
        base_url=os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai",
        ),
        api_key=os.getenv("GEMINI_API_KEY"),
    )


def resolve(task: str) -> tuple[LLMProvider, str]:
    """Return the (provider, model) configured for `task`."""
    t = task.upper()
    kind = os.getenv(f"LLM_{t}_PROVIDER", ProviderKind.OLLAMA)
    model = os.getenv(f"LLM_{t}_MODEL") or _LEGACY_MODEL_DEFAULT.get(task.lower(), SCORING_MODEL)
    return _provider_for(kind), model


def resolve_fallback(task: str) -> tuple[LLMProvider, str] | None:
    """Return the (provider, model) fallback for `task`, or None if unconfigured.

    Set LLM_<TASK>_FALLBACK_PROVIDER (+ optional LLM_<TASK>_FALLBACK_MODEL) to route
    a task to a second provider when the primary keeps failing.
    """
    t = task.upper()
    kind = os.getenv(f"LLM_{t}_FALLBACK_PROVIDER")
    if not kind:
        return None
    model = os.getenv(f"LLM_{t}_FALLBACK_MODEL") or _LEGACY_MODEL_DEFAULT.get(task.lower(), SCORING_MODEL)
    return _provider_for(kind), model


def cost(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float:
    """Estimated USD cost for a call. 0 when the model isn't in the price table."""
    rate = _COST_PER_1K.get(model)
    if not rate or prompt_tokens is None or completion_tokens is None:
        return 0.0
    p_rate, c_rate = rate
    return round(prompt_tokens / 1000 * p_rate + completion_tokens / 1000 * c_rate, 6)
