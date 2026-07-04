"""Apply services — the review-before-submit quality gate.

`review_application` gathers the JD (full if enriched), the best-matching resume variant,
and the detected ATS, then runs the AI pre-submit reviewer. It returns the verdict the
React review queue shows the user before they approve a submission. It never submits.
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.apply.ats import detect_ats
from job_hunt.apply.reviewer import review_application as _run_review
from job_hunt.services.context import context_preamble
from job_hunt.storage import repo


def _best_variant_resume(job_id: int) -> tuple[str | None, dict[str, Any]]:
    """The highest-scoring variant's slug + parsed resume for a job (or (None, {}))."""
    row = repo.best_scored_variant(job_id)
    if row is None:
        return None, {}
    return row["slug"], json.loads(row["parsed_json"])


def review_application(
    job_id: int, *, cover_letter: str = "", answers: dict[str, str] | None = None
) -> dict[str, Any]:
    """Run the AI pre-submit review for a job. Returns {job_id, ats, variant, ready, issues}."""
    repo.init_db()
    job = repo.get_job(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    jd_text = job["description_full"] or job["description"] or ""
    ats = detect_ats(job["apply_url"])
    variant_slug, resume_json = _best_variant_resume(job_id)

    verdict = _run_review(
        jd_text=jd_text, resume_json=resume_json, cover_letter=cover_letter,
        answers=answers or {}, user_context=context_preamble(),
    )
    return {"job_id": job_id, "ats": str(ats), "variant": variant_slug, **verdict}
