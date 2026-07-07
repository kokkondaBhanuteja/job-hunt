"""Home / Getting-Started status service — aggregate setup flags and live pipeline counts.

Read-only. Calls the existing service layer; never writes.
"""
from __future__ import annotations

from typing import Any

from job_hunt.enums import JobState
from job_hunt.logging_config import get_logger
from job_hunt.services.applicant import get_applicant
from job_hunt.services.apply_policy import get_policy, list_ready_to_apply
from job_hunt.services.context import get_context
from job_hunt.services.resumes import list_variants
from job_hunt.services.search_prefs import get_search_prefs
from job_hunt.services.watchlist import list_watch
from job_hunt.storage import repo

logger = get_logger(__name__)

# States that represent "scored and still needs human attention" (not yet applied/closed).
# SQL list-in-clause exception: values are enum-controlled, never user input.
_REVIEW_STATES: tuple[JobState, ...] = (
    JobState.SCORED,
    JobState.TAILORING_READY,
    JobState.DRAFTED,
    JobState.REVIEW_PENDING,
)
_REVIEW_IN = ", ".join(f"'{s.value}'" for s in _REVIEW_STATES)


def home_status() -> dict[str, Any]:
    """Return setup flags and pipeline activity counts for the Getting-Started UI."""
    repo.init_db()

    # ---- setup ----
    variants = list_variants()
    applicant = get_applicant()
    context = get_context()
    search_prefs = get_search_prefs()
    policy = get_policy()
    watchlist = list_watch()

    # ---- activity (single DB round-trip for the three counts) ----
    counts_rows = repo.raw_select(
        "SELECT "
        "(SELECT COUNT(*) FROM jobs) AS total_jobs, "
        f"(SELECT COUNT(*) FROM jobs WHERE state IN ({_REVIEW_IN})) AS new_to_review, "
        "(SELECT COUNT(*) FROM applications) AS applications"
    )
    counts = counts_rows[0] if counts_rows else {}
    total_jobs = int(counts.get("total_jobs") or 0)
    new_to_review = int(counts.get("new_to_review") or 0)
    applications_count = int(counts.get("applications") or 0)
    ready_count = len(list_ready_to_apply())

    logger.debug(
        "home_status: total_jobs=%d new_to_review=%d ready=%d apps=%d",
        total_jobs, new_to_review, ready_count, applications_count,
    )

    return {
        "setup": {
            "resume": len(variants) > 0,
            "applicant": bool(
                (applicant.get("first_name") or "").strip()
                or (applicant.get("email") or "").strip()
            ),
            "context": bool((context.get("content") or "").strip()),
            "search_prefs": bool((search_prefs.get("content") or "").strip()),
            "apply_policy": (
                int(policy.get("min_fit_score") or 0) > 0
                or bool(policy.get("must_have"))
            ),
            "watchlist_count": len(watchlist),
        },
        "activity": {
            "total_jobs": total_jobs,
            "new_to_review": new_to_review,
            "ready_to_apply": ready_count,
            "applications": applications_count,
        },
    }
