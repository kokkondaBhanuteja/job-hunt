"""In-DB event bus (transactional outbox).

Producers `emit()` an event row; the worker later `dispatch_pending()` drains
unprocessed rows and runs subscribed handlers. No external broker — the `events`
table + the worker loop are the whole bus. Kept deliberately small: only the ~7
major domain transitions plus a few infra signals.
"""
from __future__ import annotations

from typing import Any, Callable

from job_hunt.enums import EventClass, EventType
from job_hunt.logging_config import get_logger
from job_hunt.storage import repo

logger = get_logger(__name__)

# A handler that keeps failing is dead-lettered after this many attempts so it stops
# blocking the queue. Single-dispatcher assumption still holds (see dispatch_pending).
MAX_EVENT_RETRIES = 5

_DOMAIN_EVENTS = {
    EventType.JOB_DISCOVERED,
    EventType.JOB_ENRICHED,
    EventType.JOB_SCORED,
    EventType.RESUME_TAILORED,
    EventType.DRAFT_GENERATED,
    EventType.APPLICATION_SUBMITTED,
    EventType.INTERVIEW_UPDATED,
}

Handler = Callable[[dict[str, Any]], None]


def class_of(event_type: EventType) -> EventClass:
    return EventClass.DOMAIN if event_type in _DOMAIN_EVENTS else EventClass.INFRA


def emit(
    event_type: EventType,
    *,
    payload: dict[str, Any] | None = None,
    cls: EventClass | None = None,
) -> None:
    """Append an event to the outbox (analytics/automation consume it later)."""
    repo.write_event(
        type=str(event_type),
        cls=str(cls or class_of(event_type)),
        payload=payload or {},
    )


def dispatch_pending(handlers: dict[str, Handler], *, limit: int = 100) -> int:
    """Drain unprocessed events, run any matching handler, mark them processed.

    Returns the number of events successfully processed. A missing handler is fine — the
    event is still marked processed (it was recorded for analytics, not action).

    A handler that RAISES no longer blocks the queue: the event's retry_count is bumped and,
    after MAX_EVENT_RETRIES, it is dead-lettered (dead_at set) and skipped. Subsequent events
    in the batch always continue — one poison event can't freeze the pipeline.

    ASSUMES A SINGLE DISPATCHER. fetch → handle → mark is not a lease, so two concurrent
    dispatchers could both process the same event. The worker runs one dispatch loop
    (`max_instances=1`); do not run a second. A FOR UPDATE SKIP LOCKED lease is deferred.
    """
    processed = 0
    for ev in repo.fetch_unprocessed_events(limit=limit):
        handler = handlers.get(ev["type"])
        if handler is None:
            repo.mark_event_processed(ev["id"])
            processed += 1
            continue
        try:
            handler(ev)
        except Exception:  # noqa: BLE001 — one bad event must not halt the drain
            outcome = repo.record_event_failure(ev["id"], max_retries=MAX_EVENT_RETRIES)
            if outcome == "dead":
                logger.error("event %s (%s) dead-lettered after %d attempts",
                             ev["id"], ev["type"], MAX_EVENT_RETRIES)
            else:
                logger.warning("event %s (%s) handler failed; will retry (attempt %s)",
                               ev["id"], ev["type"], ev.get("retry_count", 0) + 1, exc_info=True)
            continue
        repo.mark_event_processed(ev["id"])
        processed += 1
    return processed
