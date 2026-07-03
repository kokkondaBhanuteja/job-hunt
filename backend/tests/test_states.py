"""Tests for the job state machine, event outbox, and run lifecycle (SQLite backend)."""
from __future__ import annotations

import pytest

from job_hunt import states
from job_hunt.enums import EventType, JobState, RunStatus
from job_hunt.events import bus
from job_hunt.states import InvalidTransition
from job_hunt.storage import repo


def _job(db):
    return db.insert_job_if_new(
        dedup_hash="h", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="u", posted_date=None,
    )


# ---------- state machine ----------


def test_new_job_starts_discovered(tmp_db):
    jid = _job(tmp_db)
    assert repo.get_job_state(jid) == JobState.DISCOVERED


def test_valid_transition_updates_state_audits_and_emits(tmp_db):
    jid = _job(tmp_db)
    states.transition_job(jid, JobState.SCORED, reason="auto")

    assert repo.get_job_state(jid) == JobState.SCORED
    with tmp_db.connect() as conn:
        tr = conn.execute(
            "SELECT from_state, to_state, reason FROM job_transitions WHERE job_id=?", (jid,)
        ).fetchall()
    assert [dict(r) for r in tr] == [
        {"from_state": "discovered", "to_state": "scored", "reason": "auto"}
    ]
    # JOB_SCORED event emitted (unprocessed).
    types = [e["type"] for e in repo.fetch_unprocessed_events()]
    assert str(EventType.JOB_SCORED) in types


def test_invalid_transition_raises(tmp_db):
    jid = _job(tmp_db)
    with pytest.raises(InvalidTransition):
        states.transition_job(jid, JobState.OFFER)  # discovered → offer is illegal


def test_mark_discovered_writes_initial_transition_and_event(tmp_db):
    jid = _job(tmp_db)
    states.mark_discovered(jid)
    with tmp_db.connect() as conn:
        row = conn.execute(
            "SELECT from_state, to_state FROM job_transitions WHERE job_id=?", (jid,)
        ).fetchone()
    assert row["from_state"] is None and row["to_state"] == "discovered"
    assert str(EventType.JOB_DISCOVERED) in [e["type"] for e in repo.fetch_unprocessed_events()]


# ---------- event bus ----------


def test_event_dispatch_runs_handler_and_marks_processed(tmp_db):
    bus.emit(EventType.JOB_SCORED, payload={"job_id": 7})
    seen = []
    handlers = {str(EventType.JOB_SCORED): lambda ev: seen.append(ev)}

    n = bus.dispatch_pending(handlers)
    assert n == 1
    assert seen and seen[0]["type"] == str(EventType.JOB_SCORED)
    # Now drained.
    assert repo.fetch_unprocessed_events() == []


# ---------- runs ----------


def test_run_lifecycle(tmp_db):
    rid = repo.create_run(["naukri"])
    assert repo.get_run(rid)["status"] == RunStatus.QUEUED

    repo.start_run(rid)
    assert repo.get_run(rid)["status"] == RunStatus.RUNNING

    repo.heartbeat_run(rid)  # no error
    assert repo.run_cancel_requested(rid) is False
    repo.request_run_cancel(rid)
    assert repo.run_cancel_requested(rid) is True

    repo.append_run_log(rid, "crawling page 1")
    assert "crawling page 1" in repo.get_run(rid)["log"]

    repo.finish_run(rid, RunStatus.DONE, jobs_found=5, jobs_new=2)
    run = repo.get_run(rid)
    assert run["status"] == RunStatus.DONE
    assert run["jobs_found"] == 5 and run["jobs_new"] == 2
