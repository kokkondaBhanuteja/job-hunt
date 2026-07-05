"""Search-prefs service — store the user's job-search preferences and parse them into profiles.

The user pastes a Markdown description of the roles/locations they want. The LLM parses it
into concrete search profiles (one per role×location combination) that drive discovery. The
raw markdown is also stored as a singleton so it can be retrieved later.
"""
from __future__ import annotations

from typing import Any

from job_hunt.llm.client import chat_json
from job_hunt.llm.prompts import SEARCH_PREFS
from job_hunt.logging_config import get_logger
from job_hunt.storage import repo

logger = get_logger(__name__)


def set_search_prefs(content: str) -> dict[str, Any]:
    """Store the search-prefs md and parse it into search profiles. Return {ok, profiles_created}.

    Non-destructive: adds new profiles; does not delete existing ones.
    """
    repo.init_db()
    content = content.strip()
    if not content:
        return {"error": "search preferences are empty"}
    repo.set_search_prefs(content=content)
    result = chat_json(
        content,
        schema=SEARCH_PREFS.schema,
        task="scoring",
        system=SEARCH_PREFS.system,
        prompt_name=SEARCH_PREFS.name,
        prompt_version=SEARCH_PREFS.version,
    )
    profiles = result.get("profiles") or []
    if not profiles:
        return {"error": "could not parse any search profiles from that text"}
    for p in profiles:
        repo.create_search_profile(
            name=p.get("name") or p["keywords"],
            keywords=p["keywords"],
            location=p["location"],
            pages=int(p.get("pages") or 1),
        )
    logger.info("search_prefs: created %d profile(s) from prefs", len(profiles))
    return {"ok": True, "profiles_created": len(profiles)}


def get_search_prefs() -> dict[str, Any]:
    """Return stored search-prefs ({content, updated_at}), or nulls if unset."""
    repo.init_db()
    row = repo.get_search_prefs()
    if row is None:
        return {"content": None, "updated_at": None}
    return dict(row)
