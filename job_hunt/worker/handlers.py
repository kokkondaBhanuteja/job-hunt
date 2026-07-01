"""Event handlers — the pipeline glue that makes the state machine auto-advance.

The worker's `dispatch_pending` runs these on drained events:
  JOB_DISCOVERED → enrich (fetch full JD) → (transition emits JOB_ENRICHED)
  JOB_ENRICHED   → re-score (idempotent; scores against the full JD)

`build_handlers` takes injectable fetchers + scorer so it's unit-testable without a
browser or an LLM. `default_handlers` wires the real Naukri fetcher + scorer.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from job_hunt.enrich.service import Fetcher, enrich_job
from job_hunt.enums import EventType
from job_hunt.scoring.match import score_job
from job_hunt.storage import repo


def _job_id(event: dict[str, Any]) -> int | None:
    payload = event.get("payload")
    if not payload:
        return None
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload.get("job_id")


def build_handlers(
    *,
    enrich_fetchers: dict[str, Fetcher],
    score_job_fn: Callable[[int], Any] = score_job,
) -> dict[str, Callable[[dict[str, Any]], None]]:
    def on_discovered(event: dict[str, Any]) -> None:
        job_id = _job_id(event)
        if job_id is None:
            return
        job = repo.get_job(job_id)
        if job is None:
            return
        fetch = enrich_fetchers.get(job["source"])
        if fetch is not None:
            enrich_job(job_id, fetch)

    def on_enriched(event: dict[str, Any]) -> None:
        job_id = _job_id(event)
        if job_id is None:
            return
        try:
            score_job_fn(job_id)  # score just this job, not the whole queue
        except RuntimeError:
            pass  # no resume variants yet — nothing to score

    return {
        str(EventType.JOB_DISCOVERED): on_discovered,
        str(EventType.JOB_ENRICHED): on_enriched,
    }


def default_handlers() -> dict[str, Callable[[dict[str, Any]], None]]:
    """Real handlers: each source's own enrich fetchers + the per-job scorer."""
    from job_hunt.services.enrichment import source_enrich_fetchers

    return build_handlers(enrich_fetchers=source_enrich_fetchers(headless=True))
