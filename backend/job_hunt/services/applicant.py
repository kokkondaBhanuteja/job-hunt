"""Applicant-profile services — the standing application answers, injected into form fills."""
from __future__ import annotations

from typing import Any

from job_hunt.logging_config import get_logger
from job_hunt.storage import repo
from job_hunt.storage.db import _APPLICANT_COLS

logger = get_logger(__name__)

_ALLOWED = set(_APPLICANT_COLS)


def set_applicant(fields: dict[str, Any]) -> dict[str, Any]:
    """Store/replace applicant-profile fields. Return {ok, fields} or {error}."""
    repo.init_db()
    clean = {k: v for k, v in fields.items() if k in _ALLOWED}
    unknown = set(fields) - _ALLOWED
    if unknown:
        return {"error": f"unknown field(s): {', '.join(sorted(unknown))}"}
    if not clean:
        return {"error": "no fields to set"}
    repo.set_applicant_profile(fields=clean)
    return {"ok": True, "fields": len(clean)}


def get_applicant() -> dict[str, Any]:
    """Return the applicant profile as a dict (all-null dict if unset)."""
    repo.init_db()
    row = repo.get_applicant_profile()
    if row is None:
        return {c: None for c in _APPLICANT_COLS}
    return dict(row)
