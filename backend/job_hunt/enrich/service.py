"""Enrichment service — turn a listing snippet into the full JD.

`enrich_job` is fetcher-agnostic (inject any `apply_url -> text` callable), so it's
unit-testable without a browser. `enrich_pending` drives it across DISCOVERED jobs
using a per-source fetcher map. Enriching transitions the job DISCOVERED → ENRICHED,
which emits JOB_ENRICHED — the event that (once handlers are wired) triggers re-scoring.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from job_hunt.enums import JobState
from job_hunt.states import transition_job
from job_hunt.storage import repo

Fetcher = Callable[[str], str | None]


def enrich_job(job_id: int, fetch_jd: Fetcher) -> bool:
    """Fetch + store the full JD for one job. Returns True if it was enriched.

    No-op (returns False) if the job is missing, already enriched, or the fetch is empty.
    """
    job = repo.get_job(job_id)
    if job is None or job["description_full"]:
        return False
    text = fetch_jd(job["apply_url"])
    if not text or not text.strip():
        return False

    repo.set_job_enriched(job_id, text.strip())
    try:
        transition_job(job_id, JobState.ENRICHED, reason="enriched")
    except Exception:  # noqa: BLE001 — a job past DISCOVERED still gets its JD stored
        pass
    return True


def enrich_pending(fetchers: dict[str, Fetcher], *, limit: int = 50) -> dict[str, Any]:
    """Enrich DISCOVERED jobs that lack a full JD, using each source's fetcher."""
    repo.init_db()
    candidates = [
        j for j in repo.list_scorable_jobs(limit=limit)
        if not j["description_full"] and j["state"] == JobState.DISCOVERED
    ]
    enriched = 0
    for job in candidates:
        fetch = fetchers.get(job["source"])
        if fetch is None:
            continue
        if enrich_job(int(job["id"]), fetch):
            enriched += 1
    return {"candidates": len(candidates), "enriched": enriched}
