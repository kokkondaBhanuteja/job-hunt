"""Scoring services — LLM-score pending jobs against resume variants."""
from __future__ import annotations

from job_hunt.enums import RunStatus
from job_hunt.logging_config import get_logger
from job_hunt.scoring.match import score_all_pending
from job_hunt.services.context import context_preamble
from job_hunt.storage import repo

logger = get_logger(__name__)


def score_pending(*, verbose: bool = False, track: bool = False) -> dict[str, int]:
    """Score every job that lacks a score against every variant.

    With `track=True` (the API's async trigger), the work is wrapped in a first-class `runs`
    row (queued → running → done/failed) so the Runs UI has a record + heartbeat instead of an
    invisible in-process task. Raises RuntimeError when no resume variants exist.
    """
    repo.init_db()
    user_context = context_preamble()  # inject the candidate's context into every score prompt
    if not track:
        return score_all_pending(verbose=verbose, user_context=user_context)

    run_id = repo.create_run(["score"])
    repo.start_run(run_id)
    try:
        result = score_all_pending(verbose=verbose, user_context=user_context)
    except Exception as exc:  # noqa: BLE001 — record the failure on the run, then re-raise
        logger.exception("scoring run %s failed", run_id)
        repo.finish_run(run_id, RunStatus.FAILED, errors={"error": str(exc)})
        raise
    repo.append_run_log(
        run_id,
        f"scored={result['jobs_scored']} rows={result['score_rows_written']}",
    )
    repo.finish_run(run_id, RunStatus.DONE, jobs_found=result["jobs_scored"])
    return result
