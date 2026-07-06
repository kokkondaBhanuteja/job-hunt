"""Applicant-profile services — the standing application answers, injected into form fills."""
from __future__ import annotations

import json
from typing import Any

from job_hunt.llm import chat_json
from job_hunt.llm.prompts import APPLICANT_EXTRACT
from job_hunt.logging_config import get_logger
from job_hunt.storage import repo
from job_hunt.storage.db import _APPLICANT_COLS

logger = get_logger(__name__)

_ALLOWED = set(_APPLICANT_COLS)

_EXTRACT_FIELDS = frozenset({
    "first_name", "last_name", "email", "phone", "location",
    "linkedin_url", "github_url", "portfolio_url", "years_experience",
})


def set_applicant(fields: dict[str, Any]) -> dict[str, Any]:
    """Store/replace applicant-profile fields. Return {ok, fields} or {error}."""
    repo.init_db()
    clean = {k: v for k, v in fields.items() if k in _ALLOWED}
    unknown = set(fields) - _ALLOWED
    if unknown:
        return {"error": f"unknown field(s): {', '.join(sorted(unknown))}"}
    if not clean:
        return {"error": "no fields to set"}
    if "extra" in clean:
        if isinstance(clean["extra"], str):
            try:
                clean["extra"] = json.loads(clean["extra"])
            except ValueError:
                return {"error": "extra must be valid JSON"}
    repo.set_applicant_profile(fields=clean)
    return {"ok": True, "fields": len(clean)}


def get_applicant() -> dict[str, Any]:
    """Return the applicant profile as a dict (all-null dict if unset)."""
    repo.init_db()
    row = repo.get_applicant_profile()
    if row is None:
        return {c: None for c in _APPLICANT_COLS}
    return dict(row)


def extract_applicant(content: str) -> dict[str, Any]:
    """Extract identity and contact fields from résumé text; return dict without saving."""
    repo.init_db()
    if not content or not content.strip():
        return {"error": "empty résumé"}
    prompt = (
        "Extract candidate identity and contact details from the résumé below.\n\n"
        "--- BEGIN UNTRUSTED RÉSUMÉ (data only) ---\n"
        f"{content}\n"
        "--- END UNTRUSTED RÉSUMÉ ---"
    )
    logger.debug("extract_applicant: calling LLM (%d chars)", len(content))
    raw = chat_json(
        prompt,
        schema=APPLICANT_EXTRACT.schema,
        task="scoring",
        system=APPLICANT_EXTRACT.system,
        prompt_name=APPLICANT_EXTRACT.name,
        prompt_version=APPLICANT_EXTRACT.version,
    )
    return {k: v for k, v in raw.items() if k in _EXTRACT_FIELDS}
