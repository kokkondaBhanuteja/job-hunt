"""Application services — record that a job was applied to / skipped / saved."""
from __future__ import annotations

from typing import Any

from job_hunt.enums import ApplicationOutcome, ApplicationStage, JobState
from job_hunt.states import transition_job
from job_hunt.storage import repo as db

# Allowed values derived from the enums — single source of truth.
VALID_OUTCOMES = frozenset(ApplicationOutcome)
VALID_STAGES = frozenset(ApplicationStage)

# jobs.state is the single lifecycle authority; outcomes/stages drive it (jobs.status retired).
_OUTCOME_STATE = {
    ApplicationOutcome.APPLIED: JobState.APPLIED,
    ApplicationOutcome.SKIPPED: JobState.ARCHIVED,
    ApplicationOutcome.SAVED: JobState.DEFERRED,
}
_STAGE_STATE = {
    ApplicationStage.APPLIED: JobState.APPLIED,
    ApplicationStage.OA: JobState.OA,
    ApplicationStage.INTERVIEW: JobState.INTERVIEW,
    ApplicationStage.HR: JobState.HR,
    ApplicationStage.OFFER: JobState.OFFER,
    ApplicationStage.REJECTED: JobState.REJECTED,
}


def advance_stage(job_id: int, stage: str) -> dict[str, Any]:
    """Move an application to a new interview-pipeline stage (also moves jobs.state)."""
    db.init_db()
    if stage not in VALID_STAGES:
        return {"error": f"invalid stage '{stage}'"}
    db.set_application_stage(job_id, ApplicationStage(stage))
    transition_job(job_id, _STAGE_STATE[ApplicationStage(stage)], reason="stage-advance", force=True)
    return {"ok": True, "job_id": job_id, "stage": str(stage)}


def log_application(
    job_id: int,
    variant_slug: str,
    cover_letter: str,
    status: str = ApplicationOutcome.APPLIED,
) -> dict[str, Any]:
    """Record an application outcome and move the job to `status`.

    Returns {ok, job_id, status} or {error: ...}.
    """
    db.init_db()
    if status not in VALID_OUTCOMES:
        return {"error": f"invalid status '{status}'"}

    variant_id = db.find_variant_id_by_slug(variant_slug)
    if variant_id is None:
        return {"error": f"no resume variant '{variant_slug}'"}

    if status == ApplicationOutcome.APPLIED:
        db.record_application(job_id=job_id, variant_id=variant_id, cover_letter=cover_letter)

    # jobs.state is the single lifecycle authority (jobs.status retired). Force because a
    # user may log an outcome from any state (they applied without going through tailoring).
    transition_job(job_id, _OUTCOME_STATE[ApplicationOutcome(status)], reason="logged", force=True)

    return {"ok": True, "job_id": job_id, "status": str(status)}
