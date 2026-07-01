"""Application services — record that a job was applied to / skipped / saved."""
from __future__ import annotations

from typing import Any

from job_hunt.enums import ApplicationOutcome, JobStatus
from job_hunt.storage import repo as db

# Allowed outcomes derived from the enum — single source of truth.
VALID_OUTCOMES = frozenset(ApplicationOutcome)


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

    # The outcome values map 1:1 onto job lifecycle statuses.
    db.set_job_status(job_id, JobStatus(status))

    return {"ok": True, "job_id": job_id, "status": str(status)}
