"""Drafting services — tailor a resume + write a cover letter for a job.

Both pull the job's JD (full if enriched) and its best-scoring resume variant, run the
AI Gateway, and persist the artifact. They require the job to have been scored (so there's
a best variant to work from).
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.draft.cover import generate_cover_letter
from job_hunt.draft.messages import generate_message
from job_hunt.draft.outreach import generate_outreach
from job_hunt.enums import DraftKind, JobState
from job_hunt.logging_config import get_logger
from job_hunt.resume.tailor import tailor_resume
from job_hunt.services.context import context_preamble
from job_hunt.states import advance_if_legal
from job_hunt.storage import repo

logger = get_logger(__name__)

_MESSAGE_KINDS: frozenset[DraftKind] = frozenset({
    DraftKind.THANK_YOU, DraftKind.FOLLOW_UP, DraftKind.NEGOTIATION,
})


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
    content = tailor_resume(jd_text=jd_text, resume_json=resume_json,
                            user_context=context_preamble())
    repo.save_tailored_resume(job_id=job_id, variant_id=int(variant["id"]), content=content)
    advance_if_legal(job_id, JobState.TAILORING_READY, reason="resume tailored")
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
        company=job["company"], role=job["title"], user_context=context_preamble(),
    )
    draft_id = repo.save_draft(job_id=job_id, kind=DraftKind.COVER, body=body)
    advance_if_legal(job_id, JobState.DRAFTED, reason="cover letter drafted")
    return {"job_id": job_id, "draft_id": draft_id, "kind": str(DraftKind.COVER), "body": body}


def draft_outreach_for_job(job_id: int, contact_name: str = "") -> dict[str, Any]:
    """Generate + store a recruiter-outreach message for a job."""
    repo.init_db()
    job, _variant, resume_json = _job_and_variant(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    jd_text = job["description_full"] or job["description"] or ""
    body = generate_outreach(
        jd_text=jd_text, resume_json=resume_json,
        company=job["company"], role=job["title"], contact_name=contact_name,
    )
    draft_id = repo.save_draft(job_id=job_id, kind=DraftKind.OUTREACH, body=body)
    advance_if_legal(job_id, JobState.DRAFTED, reason="outreach drafted")
    return {"job_id": job_id, "draft_id": draft_id, "kind": str(DraftKind.OUTREACH), "body": body}


def draft_message_for_job(
    job_id: int, kind: str, *, email_id: int | None = None,
) -> dict[str, Any]:
    """Generate + store a thank-you, follow-up, or negotiation message for a job."""
    try:
        dk = DraftKind(kind)
    except ValueError:
        return {"error": f"unknown kind {kind!r}"}
    if dk not in _MESSAGE_KINDS:
        return {"error": f"kind {kind!r} is not a message-draft type (use thank_you, follow_up, or negotiation)"}

    repo.init_db()
    job, _variant, resume_json = _job_and_variant(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    thread_summary = ""
    if email_id is not None:
        email_row = repo.get_email_message(email_id)
        if email_row is None:
            return {"error": f"no email with id={email_id}"}
        raw = email_row["extracted"]
        if raw:
            try:
                thread_summary = json.dumps(json.loads(raw))
            except (TypeError, ValueError):
                logger.warning("email %d extracted field is not valid JSON — skipping", email_id)

    jd_text = job["description_full"] or job["description"] or ""
    body = generate_message(
        kind,
        jd_text=jd_text,
        resume_json=resume_json,
        company=job["company"],
        role=job["title"],
        user_context=context_preamble(),
        thread_summary=thread_summary,
    )
    draft_id = repo.save_draft(job_id=job_id, kind=dk, body=body)
    advance_if_legal(job_id, JobState.DRAFTED, reason=f"{kind} message drafted")
    return {"draft_id": draft_id, "kind": str(dk), "body": body}


def list_drafts(job_id: int) -> list[dict[str, Any]]:
    repo.init_db()
    return [dict(r) for r in repo.list_drafts_for_job(job_id)]
