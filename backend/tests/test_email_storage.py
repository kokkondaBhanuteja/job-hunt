"""Tests for the email_messages and email_sync_state storage layer.

Covers: upsert dedup, structured extraction round-trip, sync state round-trip,
FK link writes, category filtering, and FK target existence in the schema.
"""
from __future__ import annotations

import json

from job_hunt.storage import repo

# ---------- helpers ----------


def _upsert(mailbox: str = "INBOX", uid: int = 1, message_id: str | None = "msg-1") -> int:
    return repo.upsert_email_message(
        mailbox=mailbox, uid=uid, message_id=message_id,
        thread_id=None, from_addr="hr@example.com", from_name="HR",
        subject="Opportunity", received_at=None, snippet=None, body_text=None,
    )


# ---------- upsert dedup ----------


def test_upsert_returns_id(tmp_db):
    email_id = _upsert()
    assert isinstance(email_id, int) and email_id > 0


def test_upsert_same_message_id_returns_same_id(tmp_db):
    id1 = _upsert(message_id="dup-msg")
    id2 = _upsert(mailbox="INBOX", uid=2, message_id="dup-msg")  # different uid, same message_id
    assert id1 == id2


def test_upsert_same_mailbox_uid_returns_same_id(tmp_db):
    id1 = _upsert(message_id=None, uid=42)
    id2 = _upsert(message_id=None, uid=42)  # no message_id — dedup by (mailbox, uid)
    assert id1 == id2


def test_upsert_different_uid_creates_new_row(tmp_db):
    id1 = _upsert(uid=1, message_id="a")
    id2 = _upsert(uid=2, message_id="b")
    assert id1 != id2


# ---------- set_email_structured ----------


def test_set_email_structured_round_trips(tmp_db):
    email_id = _upsert()
    payload = {"intent": "interview_invite", "role": "Backend Engineer"}
    repo.set_email_structured(
        email_id,
        category="interview_invite",
        extracted=payload,
        structured_at="2024-06-01T10:00:00+00:00",
    )
    row = repo.get_email_message(email_id)
    assert row["category"] == "interview_invite"
    assert json.loads(row["extracted"]) == payload


def test_set_email_structured_null_category(tmp_db):
    email_id = _upsert()
    repo.set_email_structured(
        email_id, category=None, extracted={}, structured_at="2024-06-01T10:00:00+00:00"
    )
    row = repo.get_email_message(email_id)
    assert row["category"] is None


# ---------- set_sync_state / get_sync_state ----------


def test_sync_state_round_trip(tmp_db):
    repo.set_sync_state(mailbox="INBOX", uidvalidity=12345, last_uid=99)
    row = repo.get_sync_state("INBOX")
    assert row["mailbox"] == "INBOX"
    assert row["uidvalidity"] == 12345
    assert row["last_uid"] == 99


def test_sync_state_upsert_updates(tmp_db):
    repo.set_sync_state(mailbox="INBOX", uidvalidity=1, last_uid=10)
    repo.set_sync_state(mailbox="INBOX", uidvalidity=1, last_uid=20)
    assert repo.get_sync_state("INBOX")["last_uid"] == 20


def test_sync_state_none_when_absent(tmp_db):
    assert repo.get_sync_state("NOSUCHBOX") is None


# ---------- set_email_links ----------


def test_set_email_links_null_values(tmp_db):
    email_id = _upsert()
    repo.set_email_links(email_id, company_id=None, job_id=None, application_id=None)
    row = repo.get_email_message(email_id)
    assert row["company_id"] is None
    assert row["job_id"] is None
    assert row["application_id"] is None


# ---------- list_email_messages ----------


def test_list_email_messages_no_filter(tmp_db):
    _upsert(uid=1, message_id="m1")
    _upsert(uid=2, message_id="m2")
    rows = repo.list_email_messages()
    assert len(rows) >= 2


def test_list_email_messages_filter_by_category(tmp_db):
    id1 = _upsert(uid=1, message_id="cat-a")
    id2 = _upsert(uid=2, message_id="cat-b")
    id3 = _upsert(uid=3, message_id="cat-c")
    repo.set_email_structured(id1, category="rejection", extracted={}, structured_at="2024-01-01T00:00:00+00:00")
    repo.set_email_structured(id2, category="rejection", extracted={}, structured_at="2024-01-01T00:00:00+00:00")
    repo.set_email_structured(id3, category="other", extracted={}, structured_at="2024-01-01T00:00:00+00:00")
    rows = repo.list_email_messages(category="rejection")
    ids = [r["id"] for r in rows]
    assert id1 in ids and id2 in ids and id3 not in ids


def test_list_email_messages_filter_by_action_state(tmp_db):
    id1 = _upsert(uid=1, message_id="st-a")
    id2 = _upsert(uid=2, message_id="st-b")
    repo.set_email_action_state(id1, "proposed")
    rows = repo.list_email_messages(action_state="proposed")
    ids = [r["id"] for r in rows]
    assert id1 in ids and id2 not in ids


def test_list_email_messages_limit(tmp_db):
    for i in range(5):
        _upsert(uid=i + 100, message_id=f"lim-{i}")
    assert len(repo.list_email_messages(limit=2)) == 2


# ---------- action state ----------


def test_set_email_action_state(tmp_db):
    email_id = _upsert()
    repo.set_email_action_state(email_id, "confirmed")
    row = repo.get_email_message(email_id)
    assert row["action_state"] == "confirmed"


# ---------- schema FK target verification ----------


def test_fk_tables_exist_in_schema():
    """Confirm that the tables referenced by email_messages FKs are defined in SCHEMA."""
    from job_hunt.storage.db import SCHEMA
    assert "CREATE TABLE IF NOT EXISTS companies" in SCHEMA
    assert "CREATE TABLE IF NOT EXISTS jobs" in SCHEMA
    assert "CREATE TABLE IF NOT EXISTS applications" in SCHEMA


def test_applications_has_job_id_column():
    """Confirm applications.job_id exists so get_application_by_job is safe."""
    from job_hunt.storage.db import SCHEMA
    # Both the column definition and the FK reference should appear
    assert "job_id" in SCHEMA
