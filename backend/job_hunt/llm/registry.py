"""Task → (provider, model) resolution from env. The single place that decides
whether a given task runs locally (Ollama) or against an API key.

Per task (e.g. 'scoring'), read:
    LLM_SCORING_PROVIDER   ollama | openai | gemini | groq | stub  (default: ollama)
    LLM_SCORING_MODEL      provider-specific model name

Back-compat: if LLM_<TASK>_MODEL is unset, fall back to the legacy
OLLAMA_SCORING_MODEL / OLLAMA_DRAFTING_MODEL envs (default qwen2.5:7b).
"""
from __future__ import annotations

import json
import os

from job_hunt.enums import LLMProvider as ProviderKind
from job_hunt.enums import LLMTask
from job_hunt.llm.base import LLMError, LLMProvider
from job_hunt.llm.providers.ollama import OllamaProvider
from job_hunt.llm.providers.openai_compat import OpenAICompatProvider
from job_hunt.llm.providers.stub import StubProvider
from job_hunt.logging_config import get_logger

logger = get_logger(__name__)


def _is_free(model: str) -> bool:
    """Local/stub models cost nothing — an Ollama tag ('qwen2.5:7b') or the test stub."""
    return ":" in model or model.lower() == "stub"

# Legacy defaults (preserve v0 behavior when LLM_* envs are unset).
SCORING_MODEL = os.getenv("OLLAMA_SCORING_MODEL", "qwen2.5:7b")
DRAFTING_MODEL = os.getenv("OLLAMA_DRAFTING_MODEL", "qwen2.5:7b")

_LEGACY_MODEL_DEFAULT = {LLMTask.SCORING: SCORING_MODEL, LLMTask.DRAFTING: DRAFTING_MODEL}

# Rough USD per 1K tokens (prompt, completion). 0 for local/stub. Extend via the
# LLM_COST_TABLE env (JSON: {"model": [prompt_per_1k, completion_per_1k]}) so pricing
# is config, not code — the daily report no longer silently under-reports a model it
# doesn't recognize; it warns instead.
_COST_PER_1K: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "gemini-1.5-flash": (0.000075, 0.0003),
    # Groq free-tier models: $0 so cost() returns 0.0 with no warning.
    "llama-3.3-70b-versatile": (0.0, 0.0),
    "llama-3.1-8b-instant": (0.0, 0.0),
    "llama-3.1-70b-versatile": (0.0, 0.0),
    "mixtral-8x7b-32768": (0.0, 0.0),
}


def _load_cost_table() -> dict[str, tuple[float, float]]:
    table = dict(_COST_PER_1K)
    raw = os.getenv("LLM_COST_TABLE")
    if raw:
        try:
            for model, rate in json.loads(raw).items():
                table[model] = (float(rate[0]), float(rate[1]))
        except Exception:  # noqa: BLE001
            logger.warning("LLM_COST_TABLE is not valid JSON of {model: [p, c]}; ignoring")
    return table


_COST_TABLE = _load_cost_table()
_WARNED_UNKNOWN: set[str] = set()


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
    if pk is ProviderKind.GROQ:
        raw = os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY") or ""
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        return OpenAICompatProvider(
            name=ProviderKind.GROQ,
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            api_keys=keys,
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
    model = (
        os.getenv(f"LLM_{t}_FALLBACK_MODEL")
        or _LEGACY_MODEL_DEFAULT.get(task.lower(), SCORING_MODEL)
    )
    return _provider_for(kind), model


def cost(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float:
    """Estimated USD cost for a call. 0 when the model isn't in the price table.

    Warns once per unknown model so a paid model missing from the table doesn't silently
    report $0 in the cost dashboard (add it via LLM_COST_TABLE)."""
    rate = _COST_TABLE.get(model)
    if rate is None and model not in _WARNED_UNKNOWN and not _is_free(model):
        _WARNED_UNKNOWN.add(model)
        logger.warning("no price for model '%s' — cost logged as $0 (set LLM_COST_TABLE)", model)
    if not rate or prompt_tokens is None or completion_tokens is None:
        return 0.0
    p_rate, c_rate = rate
    return round(prompt_tokens / 1000 * p_rate + completion_tokens / 1000 * c_rate, 6)
