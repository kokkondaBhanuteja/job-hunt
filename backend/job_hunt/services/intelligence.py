"""Career Intelligence Engine — explainable score breakdowns and skill-gap aggregation.

Advisory-only: all functions are read/generate; they never mutate job state,
submit applications, or trigger any downstream actions.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from job_hunt.enums import EmailActionState, EmailCategory, JobState, LearningKind
from job_hunt.llm import chat_json
from job_hunt.llm.prompts import EXPLAIN_SCORE
from job_hunt.logging_config import get_logger
from job_hunt.scoring.match import _jd_for
from job_hunt.services.context import context_preamble
from job_hunt.storage import repo

logger = get_logger(__name__)

_FOLLOWUP_DAYS = 7
_STRONG_FIT = 75

# Recruiter-originated email categories that warrant a user reply.
_REPLY_CATEGORIES = frozenset({
    EmailCategory.RECRUITER_OUTREACH,
    EmailCategory.INTERVIEW_INVITE,
})

# States where the job is closed / parked — no further action needed.
_CLOSED_STATES = frozenset({
    JobState.REJECTED,
    JobState.WITHDRAWN,
    JobState.ARCHIVED,
})

# States where a score exists but the job hasn't been applied to yet.
_SCORED_STATES = frozenset({JobState.SCORED, JobState.TAILORING_READY, JobState.DRAFTED})

# States where the job is pre-score (discovered or enriched, awaiting scoring).
_PRESCORE_STATES = frozenset({JobState.DISCOVERED, JobState.ENRICHED})


def next_best_action(job_id: int) -> dict[str, Any]:
    """Return the single highest-priority recommended action for a job — advisory only, no writes.

    Evaluates a first-match-wins rule ladder and returns
    ``{"action": str, "reason": str}`` or ``{"error": str}`` if the job is missing.
    """
    repo.init_db()

    # Rule 1: job missing.
    job = repo.get_job(job_id)
    if job is None:
        return {"error": f"no job {job_id}"}

    state_str = job["state"]
    try:
        state = JobState(state_str)
    except ValueError:
        state = None

    # Rule 2: linked recruiter email awaiting reply (highest priority — overrides state).
    for email in repo.list_emails_for_job(job_id):
        category = email["category"]
        action_state = email["action_state"]
        if category in _REPLY_CATEGORIES and action_state == EmailActionState.NONE:
            return {"action": "reply", "reason": "a recruiter email is waiting on you"}

    # Rule 3: OFFER.
    if state == JobState.OFFER:
        return {"action": "negotiate", "reason": "offer stage — draft a negotiation reply"}

    # Rule 4: INTERVIEW or HR.
    if state in (JobState.INTERVIEW, JobState.HR):
        return {"action": "prep", "reason": "interview stage — open the prep brief"}

    # Rules 5–6: APPLIED or OA — check follow-up window.
    if state in (JobState.APPLIED, JobState.OA):
        app = repo.get_application_detail(job_id)
        if app is not None:
            applied_str = app["applied_at"]
            try:
                applied_dt = datetime.fromisoformat(str(applied_str))
                # Normalise to naive UTC for comparison (SQLite stores naive UTC strings).
                if applied_dt.tzinfo is not None:
                    applied_dt = applied_dt.replace(tzinfo=None)
                now_naive = datetime.now(UTC).replace(tzinfo=None)
                days_ago = (now_naive - applied_dt).days
            except (ValueError, TypeError):
                days_ago = 0
            if days_ago >= _FOLLOWUP_DAYS and app["reply_type"] is None:
                return {
                    "action": "follow_up",
                    "reason": f"applied {days_ago} days ago, no reply — draft a follow-up",
                }
        return {"action": "wait", "reason": "applied recently — waiting on a reply"}

    # Rule 7–8: SCORED (or adjacent scored-but-not-applied states).
    if state in _SCORED_STATES:
        scores = repo.list_scores_for_job(job_id)
        best = int(scores[0]["fit_score"]) if scores else 0
        if best >= _STRONG_FIT:
            return {"action": "apply", "reason": f"strong match (score {best}) — tailor and apply"}
        return {"action": "review", "reason": f"scored {best} — review before investing time"}

    # Rule 9: ENRICHED or DISCOVERED — not scored yet.
    if state in _PRESCORE_STATES:
        return {"action": "score", "reason": "not scored yet"}

    # Rule 10: closed / terminal states.
    if state in _CLOSED_STATES:
        return {"action": "none", "reason": "closed"}

    # Rule 11: default catch-all (DEFERRED, REVIEW_PENDING, unknown).
    return {"action": "review", "reason": "review this job"}


def explain_score(job_id: int, *, force: bool = False) -> dict[str, Any]:
    """Return a per-requirement breakdown of why the résumé scored as it does for this job.

    Caches the result as a LearningKind.EXPLANATION row so repeated calls are free.
    Pass force=True to skip the cache and re-run the LLM call.
    """
    repo.init_db()

    if not force:
        cached = _cached_explanation(job_id)
        if cached is not None:
            return cached

    job = repo.get_job(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    variant = repo.best_scored_variant(job_id)
    if variant is None:
        return {"error": "score the job first"}

    resume_json = json.loads(variant["parsed_json"])
    jd_text, _ = _jd_for(job)

    preamble = context_preamble()
    prompt = _build_explain_prompt(preamble, resume_json, jd_text, job)

    result = chat_json(
        prompt,
        schema=EXPLAIN_SCORE.schema,
        task="scoring",
        system=EXPLAIN_SCORE.system,
        prompt_name=EXPLAIN_SCORE.name,
        prompt_version=EXPLAIN_SCORE.version,
    )

    scores = repo.list_scores_for_job(job_id)
    fit_score = int(scores[0]["fit_score"]) if scores else None

    payload: dict[str, Any] = {
        "matched": result.get("matched", []),
        "missing": result.get("missing", []),
        "suggestions": result.get("suggestions", []),
    }
    repo.save_learning(
        job_id=job_id,
        variant_id=int(variant["id"]),
        kind=LearningKind.EXPLANATION,
        payload=payload,
    )

    return {"job_id": job_id, "fit_score": fit_score, **payload}


def skill_gap(limit: int = 20) -> dict[str, Any]:
    """Aggregate missing requirements across all scored jobs and return the most common gaps.

    Combines LearningKind.EXPLANATION (missing[].requirement) and LearningKind.REJECTION
    (missing_keywords[]) to rank skill gaps by frequency. Advisory only.
    """
    counter: Counter[str] = Counter()
    total = 0

    for row in repo.list_learnings_by_kind(LearningKind.EXPLANATION):
        payload = _parse_payload(row["payload"])
        for item in payload.get("missing", []):
            req = item.get("requirement", "")
            if req:
                counter[req.lower().strip()] += 1
        total += 1

    for row in repo.list_learnings_by_kind(LearningKind.REJECTION):
        payload = _parse_payload(row["payload"])
        for kw in payload.get("missing_keywords", []):
            if kw:
                counter[kw.lower().strip()] += 1
        total += 1

    gaps = [
        {"skill": skill, "count": count}
        for skill, count in counter.most_common(limit)
    ]
    return {"gaps": gaps, "considered": total}


def _cached_explanation(job_id: int) -> dict[str, Any] | None:
    """Return the most recent cached EXPLANATION learning for a job, or None."""
    rows = repo.list_learnings_for_job(job_id)
    for row in rows:
        if row["kind"] == LearningKind.EXPLANATION:
            payload = _parse_payload(row["payload"])
            scores = repo.list_scores_for_job(job_id)
            fit_score = int(scores[0]["fit_score"]) if scores else None
            return {
                "job_id": job_id,
                "fit_score": fit_score,
                "matched": payload.get("matched", []),
                "missing": payload.get("missing", []),
                "suggestions": payload.get("suggestions", []),
            }
    return None


def _parse_payload(raw: Any) -> dict[str, Any]:
    """Deserialize a payload that may arrive as a string (SQLite) or dict (Postgres)."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw or {}


def _build_explain_prompt(
    preamble: str,
    resume_json: dict[str, Any],
    jd_text: str,
    job: Any,
) -> str:
    """Build the explain-score prompt combining candidate context, resume, and JD."""
    skills_flat = _flatten_skills(resume_json.get("skills") or {})
    resume_block = {
        "headline": resume_json.get("headline"),
        "summary": resume_json.get("summary"),
        "skills_flat": skills_flat,
        "experience": [
            {
                "company": e.get("company"),
                "title": e.get("title"),
                "dates": e.get("dates"),
                "bullets": e.get("bullets", [])[:5],
                "tech": e.get("tech"),
            }
            for e in (resume_json.get("experience") or [])
        ],
        "projects": [
            {"name": p.get("name"), "tech": p.get("tech")}
            for p in (resume_json.get("projects") or [])
        ],
    }
    job_block = (
        f"Title:    {job['title']}\n"
        f"Company:  {job['company']}\n"
        f"Location: {job['location'] or 'unspecified'}\n\n"
        f"--- Job Description ---\n{jd_text[:6000]}"
    )
    return (
        f"{preamble}"
        "Explain which JD requirements this résumé meets and which it misses.\n\n"
        "=== CANDIDATE RÉSUMÉ ===\n"
        f"{json.dumps(resume_block, ensure_ascii=False, indent=2)}\n\n"
        "=== JOB POSTING ===\n"
        f"{job_block}\n"
    )


def _flatten_skills(skills: dict[str, Any]) -> list[str]:
    """Flatten the grouped skills object into a single sorted list."""
    flat: list[str] = []
    for group in skills.values():
        if isinstance(group, list):
            flat.extend(str(s) for s in group)
    return sorted(flat)
