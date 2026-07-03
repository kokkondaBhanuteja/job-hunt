"""AI Gateway — the single, provider-agnostic entrypoint for LLM calls.

Services and domain modules import `chat` / `chat_json` from here (not from any
provider-named module). Routing, validation, cost logging, retries, and fallback all
happen behind these two functions.
"""
from __future__ import annotations

from job_hunt.llm.client import chat, chat_json

__all__ = ["chat", "chat_json"]
