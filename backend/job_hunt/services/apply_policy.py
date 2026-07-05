"""Apply-policy service — filter scored jobs to surface ready-to-apply candidates.

The apply policy (min_fit_score, must_have, avoid, seniority, remote_only) is stored
as a singleton keyed at id=1. list_ready_to_apply applies it as a pure filter over
already-scored jobs. This service NEVER triggers an application — the human reviews
the surfaced list and decides what to submit.
"""
from __future__ import annotations

from typing import Any

from job_hunt.logging_config import get_logger
from job_hunt.services.review import list_top_matches
from job_hunt.storage import repo

logger = get_logger(__name__)

_DEFAULTS: dict[str, Any] = {
    "min_fit_score": 0,
    "must_have": [],
    "avoid": [],
    "seniority": "",
    "remote_only": False,
}


def get_policy() -> dict[str, Any]:
    """Return the stored apply policy, or safe defaults when none is set."""
    repo.init_db()
    stored = repo.get_apply_policy()
    if stored is None:
        return dict(_DEFAULTS)
    return stored


def list_ready_to_apply(limit: int = 50) -> list[dict[str, Any]]:
    """Return scored jobs passing the apply policy — for human review only.

    Applies the stored policy as a pure filter: no email is sent, no form is filled,
    no application state is changed. The caller/human decides whether to act.
    """
    policy = get_policy()
    min_score: int = int(policy.get("min_fit_score") or 0)
    must_have: list[str] = [kw.lower() for kw in (policy.get("must_have") or [])]
    avoid: list[str] = [kw.lower() for kw in (policy.get("avoid") or [])]
    remote_only: bool = bool(policy.get("remote_only"))
    seniority: str = (policy.get("seniority") or "").lower().strip()

    matches = list_top_matches(min_score=min_score, limit=500)
    ready: list[dict[str, Any]] = []
    for match in matches:
        job = repo.get_job(match["job_id"])
        if job is None:
            continue
        text = " ".join([
            match.get("title") or "",
            match.get("company") or "",
            match.get("location") or "",
            job["description"] or "",
            job["description_full"] or "",
        ]).lower()
        if must_have and not all(kw in text for kw in must_have):
            continue
        if any(kw in text for kw in avoid):
            continue
        if remote_only and "remote" not in text:
            continue
        if seniority and seniority not in text:
            continue
        ready.append(match)
        if len(ready) >= limit:
            break
    logger.debug("apply_policy: %d/%d matches passed filter", len(ready), len(matches))
    return ready
