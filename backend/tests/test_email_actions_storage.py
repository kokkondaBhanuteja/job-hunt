"""Tests for email_actions storage layer (create, get, latest, set_result).

Hermetic — uses the tmp_db SQLite fixture; no Postgres required.
"""
from __future__ import annotations

import json

from job_hunt.storage import repo  # noqa: E402 — after stdlib, before local

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_email() -> int:
    """Insert a minimal email_messages row and return its id."""
    return repo.upsert_email_message(
        mailbox="INBOX",
        uid=1,
        message_id="<test-action-msg@example.com>",
        thread_id=None,
        from_addr="hr@example.com",
        from_name="HR",
        subject="Opportunity",
        received_at=None,
        snippet=None,
        body_text=None,
    )


# ---------------------------------------------------------------------------
# create_email_action / get_email_action round-trip
# ---------------------------------------------------------------------------


def test_create_returns_int_id(tmp_db):
    email_id = _make_email()
    action_id = repo.create_email_action(
        email_id=email_id,
        kind="draft_reply",
        payload={"body": "Hello!"},
    )
    assert isinstance(action_id, int) and action_id > 0


def test_create_get_round_trip(tmp_db):
    email_id = _make_email()
    action_id = repo.create_email_action(
        email_id=email_id,
        kind="draft_reply",
        payload={"body": "Thanks for reaching out."},
    )
    row = repo.get_email_action(action_id)
    assert row is not None
    assert row["id"] == action_id
    assert row["email_id"] == email_id
    assert row["kind"] == "draft_reply"
    assert row["state"] == "proposed"
    assert row["executed_at"] is None


def test_payload_json_round_trips(tmp_db):
    email_id = _make_email()
    payload = {"body": "Thank you!", "tone": "professional", "score": 42}
    action_id = repo.create_email_action(
        email_id=email_id, kind="draft_reply", payload=payload
    )
    row = repo.get_email_action(action_id)
    assert json.loads(row["payload"]) == payload


def test_create_apply_label(tmp_db):
    email_id = _make_email()
    action_id = repo.create_email_action(
        email_id=email_id, kind="apply_label", payload={"label": "JobHunt"}
    )
    row = repo.get_email_action(action_id)
    assert row["kind"] == "apply_label"
    assert json.loads(row["payload"]) == {"label": "JobHunt"}


def test_create_archive(tmp_db):
    email_id = _make_email()
    action_id = repo.create_email_action(
        email_id=email_id, kind="archive", payload={}
    )
    row = repo.get_email_action(action_id)
    assert row["kind"] == "archive"


def test_get_nonexistent_returns_none(tmp_db):
    assert repo.get_email_action(99999) is None


# ---------------------------------------------------------------------------
# get_latest_action_for_email
# ---------------------------------------------------------------------------


def test_get_latest_action_returns_most_recent(tmp_db):
    email_id = _make_email()
    repo.create_email_action(email_id=email_id, kind="apply_label", payload={"label": "A"})
    id2 = repo.create_email_action(email_id=email_id, kind="archive", payload={})
    row = repo.get_latest_action_for_email(email_id)
    assert row is not None
    assert row["id"] == id2
    assert row["kind"] == "archive"


def test_get_latest_action_none_when_no_actions(tmp_db):
    email_id = _make_email()
    assert repo.get_latest_action_for_email(email_id) is None


def test_get_latest_action_different_emails_isolated(tmp_db):
    email_id_a = _make_email()
    email_id_b = repo.upsert_email_message(
        mailbox="INBOX", uid=2, message_id="<b@example.com>",
        thread_id=None, from_addr="b@example.com", from_name="B",
        subject="Other", received_at=None, snippet=None, body_text=None,
    )
    id_a = repo.create_email_action(email_id=email_id_a, kind="draft_reply", payload={})
    id_b = repo.create_email_action(email_id=email_id_b, kind="archive", payload={})
    assert repo.get_latest_action_for_email(email_id_a)["id"] == id_a
    assert repo.get_latest_action_for_email(email_id_b)["id"] == id_b


# ---------------------------------------------------------------------------
# set_email_action_result
# ---------------------------------------------------------------------------


def test_set_email_action_result_updates_state(tmp_db):
    email_id = _make_email()
    action_id = repo.create_email_action(
        email_id=email_id, kind="draft_reply", payload={}
    )
    repo.set_email_action_result(
        action_id, state="executed", executed_at="2024-06-01T10:00:00+00:00"
    )
    row = repo.get_email_action(action_id)
    assert row["state"] == "executed"
    assert row["executed_at"] == "2024-06-01T10:00:00+00:00"


def test_set_email_action_result_to_failed(tmp_db):
    email_id = _make_email()
    action_id = repo.create_email_action(
        email_id=email_id, kind="archive", payload={}
    )
    repo.set_email_action_result(
        action_id, state="failed", executed_at="2024-06-01T11:00:00+00:00"
    )
    row = repo.get_email_action(action_id)
    assert row["state"] == "failed"


def test_set_email_action_result_to_dismissed(tmp_db):
    email_id = _make_email()
    action_id = repo.create_email_action(
        email_id=email_id, kind="apply_label", payload={"label": "X"}
    )
    repo.set_email_action_result(
        action_id, state="dismissed", executed_at="2024-06-01T12:00:00+00:00"
    )
    row = repo.get_email_action(action_id)
    assert row["state"] == "dismissed"
    assert row["executed_at"] == "2024-06-01T12:00:00+00:00"


def test_initial_state_is_proposed(tmp_db):
    email_id = _make_email()
    action_id = repo.create_email_action(
        email_id=email_id, kind="draft_reply", payload={}
    )
    row = repo.get_email_action(action_id)
    assert row["state"] == "proposed"
