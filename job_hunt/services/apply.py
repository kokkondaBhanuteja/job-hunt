"""Apply services — the review-before-submit quality gate.

`review_application` gathers the JD (full if enriched), the best-matching resume variant,
and the detected ATS, then runs the AI pre-submit reviewer. It returns the verdict the
React review queue shows the user before they approve a submission. It never submits.
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.apply.ats import detect_ats
from job_hunt.apply.plan import build_application_package
from job_hunt.apply.reviewer import review_application as _run_review
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
        jd_text=jd_text, resume_json=resume_json, cover_letter=cover_letter, answers=answers or {}
    )
    return {"job_id": job_id, "ats": str(ats), "variant": variant_slug, **verdict}


def _cover_body(job_id: int) -> str:
    for draft in repo.list_drafts_for_job(job_id):
        if draft["kind"] == "cover":
            return draft["body"]
    return ""


def prepare_application(
    job_id: int, screening_questions: list[str] | None = None
) -> dict[str, Any]:
    """Assemble the full application package + run the AI review — for the review queue."""
    repo.init_db()
    job = repo.get_job(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    jd_text = job["description_full"] or job["description"] or ""
    ats = detect_ats(job["apply_url"])
    variant_slug, resume_json = _best_variant_resume(job_id)
    tailored = repo.get_tailored_resume(job_id)
    cover = _cover_body(job_id)

    package = build_application_package(
        resume_content=tailored["content"] if tailored else "",
        cover_body=cover,
        screening_questions=screening_questions or [],
    )
    answers = {a["question"]: a["answer"] for a in package["answers"]}
    verdict = _run_review(jd_text=jd_text, resume_json=resume_json, cover_letter=cover, answers=answers)
    return {"job_id": job_id, "ats": str(ats), "variant": variant_slug, "package": package, **verdict}


def record_submitted_resume(job_id: int) -> dict[str, Any]:
    """Snapshot exactly what was submitted (tailored résumé, else the base variant)."""
    repo.init_db()
    variant = repo.best_scored_variant(job_id)
    tailored = repo.get_tailored_resume(job_id)
    content = tailored["content"] if tailored else (variant["parsed_json"] if variant else "")
    sid = repo.save_submitted_resume(
        job_id=job_id, variant_id=int(variant["id"]) if variant else None, content=content,
    )
    return {"job_id": job_id, "submitted_resume_id": sid}
