"""
Score each new job against each resume variant, pick the best fit.

The model returns a tight JSON: { fit_score: 0-100, reasoning: "..." }
We persist one score per (job, variant) so the dashboard / MCP server can
show which resume to send and why.
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.enums import JobState
from job_hunt.llm.ollama import chat_json
from job_hunt.llm.prompts import SCORING
from job_hunt.states import transition_job
from job_hunt.storage.repo import (
    list_jobs_for_scoring,
    list_resume_variants,
    write_score,
)


def _build_prompt(resume_json: dict[str, Any], job_row: Any) -> str:
    """Compact prompt: only the parts of the resume + job relevant to scoring."""
    resume_compact = {
        "headline": resume_json.get("headline"),
        "summary": resume_json.get("summary"),
        "skills": resume_json.get("skills"),
        "experience": [
            {
                "company": e.get("company"),
                "title": e.get("title"),
                "dates": e.get("dates"),
                "bullets": e.get("bullets", [])[:5],  # cap to keep prompt small
                "tech": e.get("tech"),
            }
            for e in (resume_json.get("experience") or [])
        ],
        "projects": [
            {"name": p.get("name"), "tech": p.get("tech")}
            for p in (resume_json.get("projects") or [])
        ],
        "tags": resume_json.get("tags"),
    }

    job_block = (
        f"Title:    {job_row['title']}\n"
        f"Company:  {job_row['company']}\n"
        f"Location: {job_row['location'] or 'unspecified'}\n"
        f"Source:   {job_row['source']}\n\n"
        f"--- Job Description ---\n"
        f"{(job_row['description'] or '')[:4000]}"
    )

    return (
        "Score this candidate-resume against this job posting.\n\n"
        "=== CANDIDATE RESUME (variant) ===\n"
        f"{json.dumps(resume_compact, ensure_ascii=False, indent=2)}\n\n"
        "=== JOB POSTING ===\n"
        f"{job_block}\n\n"
        "Return JSON: {\"fit_score\": int 0-100, \"confidence\": int 0-100, \"reasoning\": \"...\"}."
    )


def score_one(resume_json: dict[str, Any], job_row: Any) -> dict[str, Any]:
    """Score one (variant, job) pair. Returns {'fit_score': int, 'reasoning': str}."""
    return chat_json(
        _build_prompt(resume_json, job_row),
        schema=SCORING.schema,
        task="scoring",
        system=SCORING.system,
        temperature=0.1,
    )


def score_all_pending(*, verbose: bool = False) -> dict[str, int]:
    """Iterate every new job × every resume variant; persist scores.

    Returns a small summary dict: {jobs_scored: N, score_rows_written: N}.
    """
    variants = list_resume_variants()
    if not variants:
        raise RuntimeError(
            "No resume variants in DB. Run `parse-resume` on your vault first."
        )

    pending = list_jobs_for_scoring()
    jobs_scored = 0
    rows_written = 0

    for job in pending:
        for variant in variants:
            try:
                resume_json = json.loads(variant["parsed_json"])
                result = score_one(resume_json, job)
                confidence = result.get("confidence")
                write_score(
                    job_id=int(job["id"]),
                    variant_id=int(variant["id"]),
                    fit_score=int(result["fit_score"]),
                    reasoning=str(result["reasoning"]),
                    confidence=int(confidence) if confidence is not None else None,
                )
                rows_written += 1
                if verbose:
                    print(
                        f"  [{variant['slug']:>16}] {result['fit_score']:3d} "
                        f"| {job['company'][:25]:<25} | {job['title'][:50]}"
                    )
            except Exception as exc:  # noqa: BLE001 — log + continue
                if verbose:
                    print(f"  ! score failed for job={job['id']} variant={variant['slug']}: {exc}")
                continue
        jobs_scored += 1
        # Advance the state machine (emits JOB_SCORED). Guarded: a job already past
        # SCORED shouldn't abort the batch.
        try:
            transition_job(int(job["id"]), JobState.SCORED, reason="auto-scored")
        except Exception:  # noqa: BLE001
            pass

    return {"jobs_scored": jobs_scored, "score_rows_written": rows_written}
