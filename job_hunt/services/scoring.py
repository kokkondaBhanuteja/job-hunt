"""Scoring services — LLM-score pending jobs against resume variants."""
from __future__ import annotations

from job_hunt.scoring.match import score_all_pending
from job_hunt.storage.repo import init_db


def score_pending(*, verbose: bool = False) -> dict[str, int]:
    """Score every job that lacks a score against every variant.

    Raises RuntimeError when no resume variants exist (parse the vault first).
    Returns {jobs_scored, score_rows_written}.
    """
    init_db()
    return score_all_pending(verbose=verbose)
