"""In-DB event bus (transactional outbox).

Producers `emit()` an event row; the worker later `dispatch_pending()` drains
unprocessed rows and runs subscribed handlers. No external broker — the `events`
table + the worker loop are the whole bus. Kept deliberately small: only the ~7
major domain transitions plus a few infra signals.
"""
from __future__ import annotations

from typing import Any, Callable

from job_hunt.enums import EventClass, EventType
from job_hunt.storage import repo

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

    Returns the number of events processed. A missing handler is fine — the event
    is still marked processed (it was recorded for analytics, not action).
    """
    processed = 0
    for ev in repo.fetch_unprocessed_events(limit=limit):
        handler = handlers.get(ev["type"])
        if handler is not None:
            handler(ev)
        repo.mark_event_processed(ev["id"])
        processed += 1
    return processed
