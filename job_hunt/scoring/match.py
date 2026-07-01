"""
Score each scorable job against each resume variant, pick the best fit.

Scoring is **idempotent**: a (job, variant) pair is only (re)scored when the JD text
it would score against — or the scoring model — has changed since last time. So a
re-run after enrichment re-scores against the full JD exactly once, and a plain re-run
does nothing (and bills nothing). Prompts/schema come from the Prompt Library.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from job_hunt.enums import JobState
from job_hunt.llm import registry
from job_hunt.llm import chat_json
from job_hunt.llm.prompts import SCORING
from job_hunt.logging_config import get_logger
from job_hunt.states import can_transition, transition_job
from job_hunt.storage import repo
from job_hunt.storage.repo import (
    list_resume_variants,
    list_scorable_jobs,
    scores_meta_for_job,
    write_score,
)

logger = get_logger(__name__)


def _jd_for(job: Any) -> tuple[str, str]:
    """The best JD text available for a job + which kind it is ('full' | 'snippet')."""
    full = job["description_full"]
    if full:
        return full, "full"
    return (job["description"] or ""), "snippet"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_prompt(resume_json: dict[str, Any], job_row: Any, jd_text: str) -> str:
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
        f"{jd_text[:6000]}"
    )

    return (
        "Score this candidate-resume against this job posting.\n\n"
        "=== CANDIDATE RESUME (variant) ===\n"
        f"{json.dumps(resume_compact, ensure_ascii=False, indent=2)}\n\n"
        "=== JOB POSTING ===\n"
        f"{job_block}\n\n"
        "Return JSON: {\"fit_score\": int 0-100, \"confidence\": int 0-100, \"reasoning\": \"...\"}."
    )


def score_one(resume_json: dict[str, Any], job_row: Any, jd_text: str) -> dict[str, Any]:
    """Score one (variant, job) pair. Returns {'fit_score', 'confidence', 'reasoning'}."""
    return chat_json(
        _build_prompt(resume_json, job_row, jd_text),
        schema=SCORING.schema,
        task="scoring",
        system=SCORING.system,
        temperature=0.1,
    )


def score_all_pending(*, verbose: bool = False) -> dict[str, int]:
    """(Re)score every scorable job × variant whose JD/model changed since last time.

    Returns {jobs_scored: N, score_rows_written: N}. Idempotent: unchanged pairs are skipped.
    """
    variants = list_resume_variants()
    if not variants:
        raise RuntimeError(
            "No resume variants in DB. Run `parse-resume` on your vault first."
        )
    provider_model = _provider_model()

    jobs = list(list_scorable_jobs())
    # One batched query for all existing-score metadata instead of one per job (idempotency N+1).
    meta_by_job = repo.scores_meta_for_jobs([int(j["id"]) for j in jobs])

    jobs_scored = 0
    rows_written = 0
    for job in jobs:
        wrote = _score_job_row(
            job, variants, provider_model,
            existing_meta=meta_by_job.get(int(job["id"]), []), verbose=verbose,
        )
        rows_written += wrote
        if wrote:
            jobs_scored += 1
    return {"jobs_scored": jobs_scored, "score_rows_written": rows_written}


def score_job(job_id: int) -> dict[str, int]:
    """(Re)score a SINGLE job × variants — what the JOB_ENRICHED event handler calls."""
    variants = list_resume_variants()
    if not variants:
        raise RuntimeError("No resume variants in DB. Run `parse-resume` first.")
    job = repo.get_job(job_id)
    if job is None:
        return {"jobs_scored": 0, "score_rows_written": 0}
    wrote = _score_job_row(job, variants, _provider_model())
    return {"jobs_scored": 1 if wrote else 0, "score_rows_written": wrote}


def _provider_model() -> str:
    provider, model = registry.resolve("scoring")
    return f"{provider.name}:{model}"


def _score_job_row(
    job: Any, variants: Any, provider_model: str, *,
    existing_meta: Any = None, verbose: bool = False,
) -> int:
    """Score one job row against every variant (idempotent). Returns rows written.

    `existing_meta` lets a batch caller pass this job's score metadata (pre-fetched in one
    query); a single-job caller leaves it None and it's fetched here.
    """
    jd_text, scored_against = _jd_for(job)
    input_hash = _hash(jd_text)
    meta_rows = existing_meta if existing_meta is not None else scores_meta_for_job(int(job["id"]))
    existing = {
        int(r["variant_id"]): (r["input_hash"], r["provider_model"]) for r in meta_rows
    }

    wrote = 0
    for variant in variants:
        vid = int(variant["id"])
        if existing.get(vid) == (input_hash, provider_model):
            continue  # already scored against this exact JD + model → skip (idempotent)
        try:
            resume_json = json.loads(variant["parsed_json"])
            result = score_one(resume_json, job, jd_text)
            confidence = result.get("confidence")
            write_score(
                job_id=int(job["id"]), variant_id=vid, fit_score=int(result["fit_score"]),
                reasoning=str(result["reasoning"]),
                confidence=int(confidence) if confidence is not None else None,
                scored_against=scored_against, input_hash=input_hash, provider_model=provider_model,
            )
            wrote += 1
            if verbose:
                print(f"  [{variant['slug']:>16}] {result['fit_score']:3d} ({scored_against}) "
                      f"| {job['company'][:25]:<25} | {job['title'][:50]}")
        except Exception:  # noqa: BLE001 — log + continue (don't let one variant kill the scan)
            logger.warning("scoring failed for job=%s variant=%s",
                           job["id"], variant["slug"], exc_info=True)
            continue

    if wrote:  # advance the state machine only from a legal source state (no silent swallow)
        current = JobState(repo.get_job_state(int(job["id"])))
        if can_transition(current, JobState.SCORED):
            transition_job(int(job["id"]), JobState.SCORED, reason="auto-scored")
    return wrote
