"""Event handlers — the pipeline glue that makes the state machine auto-advance.

The worker's `dispatch_pending` runs these on drained events:
  JOB_DISCOVERED → enrich (fetch full JD) → (transition emits JOB_ENRICHED)
  JOB_ENRICHED   → re-score (idempotent; scores against the full JD)
  JOB_SCORED     → instant alert if the job clears the apply policy (alert-only, no state change)

`build_handlers` takes injectable fetchers + scorer so it's unit-testable without a
browser or an LLM. `default_handlers` wires the real Naukri fetcher + scorer.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from job_hunt.enrich.service import Fetcher, enrich_job
from job_hunt.enums import EventType, LearningKind
from job_hunt.logging_config import get_logger
from job_hunt.notify.base import get_notifier
from job_hunt.scoring.match import score_job
from job_hunt.services import apply_policy as _ap
from job_hunt.services.context import context_preamble
from job_hunt.storage import repo

logger = get_logger(__name__)


def _job_id(event: dict[str, Any]) -> int | None:
    payload = event.get("payload")
    if not payload:
        return None
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload.get("job_id")


def _score_job_with_context(job_id: int) -> Any:
    """Default auto-scorer — injects the user's context so auto-scored jobs reflect them too."""
    return score_job(job_id, user_context=context_preamble())


def build_handlers(
    *,
    enrich_fetchers: dict[str, Fetcher],
    score_job_fn: Callable[[int], Any] = _score_job_with_context,
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


def on_scored(event: dict[str, Any]) -> None:
    """Handle JOB_SCORED: push an instant alert when the job clears the apply policy.

    Alert-only — no state transition, no auto-apply. Deduped via a LearningKind.ALERT
    marker so a re-score of the same job never fires a second notification.
    """
    try:
        job_id = _job_id(event)
        if job_id is None:
            return
        job_row = repo.get_job(job_id)
        if job_row is None:
            return
        scores = repo.list_scores_for_job(job_id)
        if not scores:
            return
        fit_score: int = int(scores[0]["fit_score"])
        policy = _ap.get_policy()
        min_score: int = int(policy.get("min_fit_score") or 0)
        if fit_score < min_score:
            return
        job = dict(job_row)
        if not _ap.passes_policy(job, policy):
            return
        # dedup: skip if we already sent an alert for this job
        learnings = repo.list_learnings_for_job(job_id)
        if any(row["kind"] == str(LearningKind.ALERT) for row in learnings):
            return
        title: str = job.get("title") or ""
        company: str = job.get("company") or ""
        apply_url: str = job.get("apply_url") or ""
        # Write the dedup marker BEFORE sending — a partially-failed send can't
        # trigger a duplicate alert on the next dispatch.
        repo.save_learning(
            job_id=job_id,
            variant_id=None,
            kind=LearningKind.ALERT,
            payload={"fit_score": fit_score, "title": title, "company": company},
        )
        get_notifier().send(
            f"\U0001f514 New match: {title} @ {company} — score {fit_score}\n{apply_url}"
        )
    except Exception:
        logger.exception("on_scored: unhandled error for event %s", event.get("id"))


def default_handlers() -> dict[str, Callable[[dict[str, Any]], None]]:
    """Real handlers: each source's own enrich fetchers + the per-job scorer."""
    from job_hunt.services.enrichment import source_enrich_fetchers

    handlers = build_handlers(enrich_fetchers=source_enrich_fetchers(headless=True))
    handlers[str(EventType.JOB_SCORED)] = on_scored
    return handlers
