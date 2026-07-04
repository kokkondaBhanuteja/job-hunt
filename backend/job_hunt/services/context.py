"""User-context services — one editable career-context blob the AI always sees.

The user pastes a résumé/context (Markdown or JSON, produced however they like) and it is
injected as an "About the candidate" preamble into every scoring / tailoring / drafting /
review prompt. No parsing, no retrieval — the blob is résumé-sized, so the whole thing is the
context. This augments (does not replace) the résumé-variant flow.
"""
from __future__ import annotations

from typing import Any

from job_hunt.enums import ContextFormat
from job_hunt.logging_config import get_logger
from job_hunt.storage import repo

logger = get_logger(__name__)

_MAX_PREAMBLE_CHARS = 6000


def set_context(content: str, fmt: str) -> dict[str, Any]:
    """Store (or replace) the user's career context. Return {ok, format, length} or {error}."""
    repo.init_db()
    content = content.strip()
    if not content:
        return {"error": "context is empty"}
    if fmt not in set(ContextFormat):
        return {"error": f"invalid format '{fmt}' (use 'md' or 'json')"}
    repo.set_user_context(content=content, fmt=fmt)
    return {"ok": True, "format": str(fmt), "length": len(content)}


def get_context() -> dict[str, Any]:
    """Return the stored user context ({content, format, updated_at}), or nulls if unset."""
    repo.init_db()
    row = repo.get_user_context()
    if row is None:
        return {"content": None, "format": None, "updated_at": None}
    return dict(row)


def context_preamble() -> str:
    """Return the 'About the candidate' preamble to inject into prompts, or '' if unset.

    Best-effort: a failure here (e.g. table missing) must never break a prompt build.
    """
    try:
        row = repo.get_user_context()
    except Exception:  # noqa: BLE001 — context is an enhancement; never break scoring/drafting
        logger.debug("user-context lookup failed; proceeding without preamble", exc_info=True)
        return ""
    if row is None:
        return ""
    content = str(row["content"])[:_MAX_PREAMBLE_CHARS]
    return f"About the candidate (their own words — treat as ground truth):\n{content}\n\n"
