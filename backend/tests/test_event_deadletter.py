"""A1: a poison event (handler always raises) must not block the queue — it retries then
dead-letters, and other events keep draining."""
from __future__ import annotations

from job_hunt.enums import EventType
from job_hunt.events import bus


def _emit(ev_type: EventType, **payload) -> None:
    bus.emit(ev_type, payload=payload)


def test_poison_event_deadletters_and_does_not_block(tmp_db):
    # A poison event first, then a good one — the good one must still be processed.
    _emit(EventType.JOB_DISCOVERED, job_id=1)   # poison target
    _emit(EventType.JOB_ENRICHED, job_id=2)     # should always drain

    good_seen: list[int] = []
    handlers = {
        str(EventType.JOB_DISCOVERED): lambda ev: (_ for _ in ()).throw(RuntimeError("boom")),
        str(EventType.JOB_ENRICHED): lambda ev: good_seen.append(ev["payload"]),
    }

    # Drain MAX_EVENT_RETRIES times: the good event processes on cycle 1; the poison one
    # keeps failing and is dead-lettered exactly on the last attempt.
    for _ in range(bus.MAX_EVENT_RETRIES):
        bus.dispatch_pending(handlers)

    assert len(good_seen) == 1  # good event drained despite the poison one (no head-of-line block)

    with tmp_db.connect() as conn:
        poison = conn.execute(
            "SELECT retry_count, dead_at FROM events WHERE type = ?",
            (str(EventType.JOB_DISCOVERED),),
        ).fetchone()
    assert poison["retry_count"] == bus.MAX_EVENT_RETRIES
    assert poison["dead_at"] is not None  # dead-lettered → no longer fetched


def test_recovering_handler_marks_processed(tmp_db):
    _emit(EventType.JOB_SCORED, job_id=9)
    fail = {"n": 0}

    def flaky(ev):
        fail["n"] += 1
        if fail["n"] < 2:
            raise RuntimeError("transient")

    handlers = {str(EventType.JOB_SCORED): flaky}
    bus.dispatch_pending(handlers)  # fails → retry_count 1
    bus.dispatch_pending(handlers)  # succeeds → processed

    with tmp_db.connect() as conn:
        row = conn.execute(
            "SELECT processed_at, dead_at FROM events WHERE type = ?",
            (str(EventType.JOB_SCORED),),
        ).fetchone()
    assert row["processed_at"] is not None and row["dead_at"] is None
