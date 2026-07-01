"""Drafting services — tailor a resume + write a cover letter for a job.

Both pull the job's JD (full if enriched) and its best-scoring resume variant, run the
AI Gateway, and persist the artifact. They require the job to have been scored (so there's
a best variant to work from).
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.draft.cover import generate_cover_letter
from job_hunt.enums import DraftKind
from job_hunt.resume.tailor import tailor_resume
from job_hunt.storage import repo


def _job_and_variant(job_id: int) -> tuple[dict[str, Any] | None, Any, dict[str, Any]]:
    job = repo.get_job(job_id)
    if job is None:
        return None, None, {}
    variant = repo.best_scored_variant(job_id)
    resume_json = json.loads(variant["parsed_json"]) if variant else {}
    return job, variant, resume_json


def tailor_for_job(job_id: int) -> dict[str, Any]:
    """Generate + store a JD-tailored resume for a job's best variant."""
    repo.init_db()
    job, variant, resume_json = _job_and_variant(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}
    if variant is None:
        return {"error": "job is not scored yet — nothing to tailor"}

    jd_text = job["description_full"] or job["description"] or ""
    content = tailor_resume(jd_text=jd_text, resume_json=resume_json)
    repo.save_tailored_resume(job_id=job_id, variant_id=int(variant["id"]), content=content)
    return {"job_id": job_id, "variant": variant["slug"], "content": content}


def draft_cover_for_job(job_id: int) -> dict[str, Any]:
    """Generate + store a cover letter for a job."""
    repo.init_db()
    job, _variant, resume_json = _job_and_variant(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    jd_text = job["description_full"] or job["description"] or ""
    body = generate_cover_letter(
        jd_text=jd_text, resume_json=resume_json,
        company=job["company"], role=job["title"],
    )
    draft_id = repo.save_draft(job_id=job_id, kind=DraftKind.COVER, body=body)
    return {"job_id": job_id, "draft_id": draft_id, "kind": str(DraftKind.COVER), "body": body}


def list_drafts(job_id: int) -> list[dict[str, Any]]:
    repo.init_db()
    return [dict(r) for r in repo.list_drafts_for_job(job_id)]
