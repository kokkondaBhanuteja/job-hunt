"""Job state machine — allowed transitions, the event each state emits, and the
single `transition_job()` entry point that validates + audits + emits.

Keeping the graph here (not scattered across services) means the legal lifecycle
is one readable thing, and every state change goes through one audited path.
"""
from __future__ import annotations

from job_hunt.enums import EventType, JobState
from job_hunt.events import bus
from job_hunt.storage import repo

S = JobState

# Legal transitions. A state absent from a target set cannot be reached from there.
ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    S.DISCOVERED:      {S.ENRICHED, S.SCORED, S.ARCHIVED, S.WITHDRAWN},
    S.ENRICHED:        {S.SCORED, S.ARCHIVED, S.WITHDRAWN},
    S.SCORED:          {S.OPPORTUNITY, S.ARCHIVED, S.DEFERRED, S.WITHDRAWN},
    S.OPPORTUNITY:     {S.TAILORING_READY, S.DEFERRED, S.ARCHIVED, S.WITHDRAWN},
    S.TAILORING_READY: {S.DRAFTED, S.DEFERRED, S.WITHDRAWN},
    S.DRAFTED:         {S.REVIEW_PENDING, S.DEFERRED, S.WITHDRAWN},
    S.REVIEW_PENDING:  {S.READY_TO_APPLY, S.DEFERRED, S.ARCHIVED, S.WITHDRAWN},
    S.READY_TO_APPLY:  {S.APPLIED, S.DEFERRED, S.WITHDRAWN},
    S.APPLIED:         {S.OA, S.INTERVIEW, S.REJECTED, S.WITHDRAWN},
    S.OA:              {S.INTERVIEW, S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW:       {S.HR, S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.HR:              {S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.OFFER:           {S.WITHDRAWN},
    S.REJECTED:        set(),
    S.ARCHIVED:        {S.OPPORTUNITY},
    S.DEFERRED:        {S.OPPORTUNITY, S.TAILORING_READY, S.READY_TO_APPLY, S.ARCHIVED, S.WITHDRAWN},
    S.WITHDRAWN:       set(),
}

# Entering a state emits its major domain event (states not listed emit nothing).
STATE_EVENT: dict[JobState, EventType] = {
    S.DISCOVERED:      EventType.JOB_DISCOVERED,
    S.ENRICHED:        EventType.JOB_ENRICHED,
    S.SCORED:          EventType.JOB_SCORED,
    S.TAILORING_READY: EventType.RESUME_TAILORED,
    S.DRAFTED:         EventType.DRAFT_GENERATED,
    S.APPLIED:         EventType.APPLICATION_SUBMITTED,
    S.OA:              EventType.INTERVIEW_UPDATED,
    S.INTERVIEW:       EventType.INTERVIEW_UPDATED,
    S.HR:              EventType.INTERVIEW_UPDATED,
    S.OFFER:           EventType.INTERVIEW_UPDATED,
}


class InvalidTransition(ValueError):
    """Raised when a state change isn't allowed by the machine."""


def can_transition(src: JobState, dst: JobState) -> bool:
    return dst in ALLOWED_TRANSITIONS.get(src, set())


def transition_job(job_id: int, to_state: JobState, *, reason: str = "") -> JobState:
    """Validate, persist (audit + state), and emit the entered state's event."""
    current = JobState(repo.get_job_state(job_id))
    if not can_transition(current, to_state):
        raise InvalidTransition(f"job {job_id}: {current} → {to_state} not allowed")

    repo.write_job_transition(job_id=job_id, from_state=str(current), to_state=str(to_state), reason=reason)
    repo.set_job_state(job_id, to_state)

    event = STATE_EVENT.get(to_state)
    if event is not None:
        bus.emit(event, payload={"job_id": job_id})
    return to_state


def mark_discovered(job_id: int, *, reason: str = "scrape") -> None:
    """Record the initial DISCOVERED state for a freshly-inserted job (audit + event)."""
    repo.write_job_transition(job_id=job_id, from_state=None, to_state=str(S.DISCOVERED), reason=reason)
    bus.emit(EventType.JOB_DISCOVERED, payload={"job_id": job_id})
