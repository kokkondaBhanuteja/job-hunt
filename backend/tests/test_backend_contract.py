"""C1/C2: contract tests run the SAME assertions against BOTH backends, so the 786 lines of
hand-written Postgres SQL are proven to behave identically to SQLite — not just assumed.

Postgres is exercised against the dev DB (gated on reachability) and every row created here is
namespaced (`company='ContractCo'`, slugs `contract-*`) and cleaned up before + after.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from job_hunt.enums import JobState, OutreachStatus
from job_hunt.storage import db as sqlite_db
from job_hunt.storage import pg


def _pg_available() -> bool:
    try:
        with pg.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


_PG = _pg_available()


def _pg_cleanup() -> None:
    with pg.connect() as conn:
        conn.execute("DELETE FROM scores WHERE job_id IN (SELECT id FROM jobs WHERE company='ContractCo')")
        conn.execute("DELETE FROM job_transitions WHERE job_id IN (SELECT id FROM jobs WHERE company='ContractCo')")
        conn.execute("DELETE FROM events WHERE (payload->>'job_id')::int IN (SELECT id FROM jobs WHERE company='ContractCo')")
        conn.execute("DELETE FROM jobs WHERE company='ContractCo'")
        conn.execute("DELETE FROM resume_variants WHERE slug LIKE 'contract-%'")
        conn.execute("DELETE FROM contacts WHERE company='ContractCo'")  # cascades to outreach


@pytest.fixture(params=["sqlite", "postgres"])
def backend(request, tmp_path, monkeypatch):
    if request.param == "sqlite":
        path = tmp_path / "contract.db"
        monkeypatch.setattr(sqlite_db, "DB_PATH", path)
        sqlite_db.init_db(path)
        yield sqlite_db
    else:
        if not _PG:
            pytest.skip("Postgres not reachable")
        pg.init_db()
        _pg_cleanup()
        yield pg
        _pg_cleanup()


def _seed(backend):
    v_lo = backend.upsert_resume_variant(slug="contract-lo", source_path="/a", parsed={"h": 1}, tags=[])
    v_hi = backend.upsert_resume_variant(slug="contract-hi", source_path="/b", parsed={"h": 1}, tags=[])
    jid = backend.insert_job_if_new(
        dedup_hash="contract-1", source="naukri", source_job_id=None, title="Backend Engineer",
        company="ContractCo", location="blr", description="d", apply_url="u", posted_date=None,
        emit_discovered=True,
    )
    backend.write_score(job_id=jid, variant_id=v_lo, fit_score=70, reasoning="lo")
    backend.write_score(job_id=jid, variant_id=v_hi, fit_score=90, reasoning="hi")
    return jid


def test_top_matches_winning_variant_parity(backend):
    jid = _seed(backend)
    mine = [r for r in backend.top_matches(min_score=60, limit=200) if r["job_id"] == jid]
    assert len(mine) == 1                          # exactly one row per job on both backends
    assert mine[0]["best_score"] == 90
    assert mine[0]["best_variant"] == "contract-hi"  # deterministic winning variant


def test_list_board_jobs_parity(backend):
    jid = _seed(backend)
    mine = [r for r in backend.list_board_jobs(limit=500) if r["id"] == jid]
    assert len(mine) == 1
    assert mine[0]["best_score"] == 90
    assert mine[0]["state"] == "discovered"


def test_insert_dedup_returns_none_parity(backend):
    _seed(backend)
    dup = backend.insert_job_if_new(
        dedup_hash="contract-1", source="naukri", source_job_id=None, title="BE",
        company="ContractCo", location="blr", description="d", apply_url="u", posted_date=None,
    )
    assert dup is None


def test_apply_transition_atomicity_parity(backend):
    jid = _seed(backend)
    backend.apply_transition(
        job_id=jid, from_state="discovered", to_state="enriched", reason="t",
        event_type="job.enriched", event_class="domain", payload={"job_id": jid},
    )
    assert backend.get_job_state(jid) == "enriched"
    trans = backend.raw_select(
        f"SELECT count(*) AS c FROM job_transitions WHERE job_id={jid} AND to_state='enriched'"
    )[0]["c"]
    assert trans == 1  # state + audit row committed together on both backends


def test_state_check_matches_enum_parity(backend):
    """Every current JobState value must be accepted by the CHECK on both backends (catches the
    hardcoded-Postgres-CHECK vs enum-derived-SQLite-CHECK drift), and a bogus value rejected."""
    jid = backend.insert_job_if_new(
        dedup_hash="contract-chk", source="naukri", source_job_id=None, title="BE",
        company="ContractCo", location="blr", description="d", apply_url="u", posted_date=None,
    )
    for state in JobState:
        backend.set_job_state(jid, state)  # must not raise on either backend
        assert backend.get_job_state(jid) == str(state)
    # noqa target: the CHECK-violation type differs per backend (sqlite3.IntegrityError vs
    # psycopg.errors.CheckViolation), so a broad Exception is the correct cross-backend assert.
    with pytest.raises(Exception):  # noqa: B017
        backend.set_job_state(jid, "definitely-not-a-state")


def test_raw_select_rejects_mutations_parity(backend):
    for bad in ("DELETE FROM jobs", "DROP TABLE jobs", "UPDATE jobs SET state='x'",
                "  delete from jobs", "-- x\nDROP TABLE jobs"):
        with pytest.raises(ValueError):
            backend.raw_select(bad)


def test_pg_raw_select_readonly_blocks_piggyback():
    """The prefix guard passes 'SELECT …; DELETE …' (starts with SELECT), but the read-only
    transaction must stop the mutation from running."""
    if not _PG:
        pytest.skip("Postgres not reachable")
    pg.init_db()
    before = pg.raw_select("SELECT count(*) AS c FROM jobs")[0]["c"]
    # psycopg raises one of several error types for a read-only-tx violation / multi-statement;
    # a broad Exception is the right assert here.
    with pytest.raises(Exception):  # noqa: B017
        pg.raw_select("SELECT 1; DELETE FROM jobs")
    after = pg.raw_select("SELECT count(*) AS c FROM jobs")[0]["c"]
    assert before == after  # nothing deleted


# ---------- outreach (cold email) ----------


def _iso(delta: timedelta = timedelta(0)) -> str:
    return (datetime.now(UTC) + delta).isoformat(timespec="seconds")


def _draft(backend, *, to_email: str = "priya@contractco.com", parent_id: int | None = None) -> int:
    contact_id = backend.save_contact(company="ContractCo", name="Priya")
    return backend.insert_outreach(
        contact_id=contact_id, to_email=to_email, subject="Backend role", body="Hello",
        mailto_url="mailto:x", template_slug="cold_email@1", parent_id=parent_id,
    )


def _send(backend, oid: int) -> None:
    assert backend.claim_outreach_for_send(oid) is True
    backend.set_outreach_sent(oid, message_id=f"<{oid}@test>")


def test_outreach_insert_get_list_parity(backend):
    oid = _draft(backend)
    row = backend.get_outreach(oid)
    assert row["status"] == OutreachStatus.DRAFT
    assert (row["company"], row["contact_name"], row["to_email"]) == (
        "ContractCo", "Priya", "priya@contractco.com",
    )
    assert oid in [r["id"] for r in backend.list_outreach(status=OutreachStatus.DRAFT)]
    assert backend.get_outreach(10**9) is None


def test_outreach_claim_is_exactly_once(backend):
    oid = _draft(backend)
    since = _iso(-timedelta(minutes=1))
    before = backend.count_outreach_sent_since(since)
    _send(backend, oid)
    assert backend.claim_outreach_for_send(oid) is False  # a second send can't claim it
    row = backend.get_outreach(oid)
    assert row["status"] == OutreachStatus.SENT and row["message_id"] == f"<{oid}@test>"
    assert row["sent_at"] is not None
    assert backend.count_outreach_sent_since(since) == before + 1
    assert backend.update_outreach_draft(oid, subject="x", body="y", to_email="z@z.com") is False


def test_outreach_failed_can_be_edited_and_reclaimed(backend):
    oid = _draft(backend)
    assert backend.claim_outreach_for_send(oid) is True
    backend.set_outreach_failed(oid, error="SMTPAuthenticationError")
    row = backend.get_outreach(oid)
    assert (row["status"], row["last_error"]) == (OutreachStatus.FAILED, "SMTPAuthenticationError")
    assert backend.update_outreach_draft(oid, subject="s2", body="b2", to_email="p@contractco.com")
    assert backend.claim_outreach_for_send(oid) is True
    assert backend.get_outreach(oid)["last_error"] is None


def test_outreach_cancel_parity(backend):
    oid = _draft(backend)
    assert backend.set_outreach_cancelled(oid) is True
    assert backend.set_outreach_cancelled(oid) is False
    assert backend.claim_outreach_for_send(oid) is False


def test_outreach_reply_marks_only_sent_rows_case_insensitively(backend):
    sent = _draft(backend, to_email="Priya@ContractCo.com")
    _send(backend, sent)
    draft = _draft(backend, to_email="priya@contractco.com")
    assert backend.mark_outreach_replied(["PRIYA@contractco.com", "", "other@x.com"]) == [sent]
    assert backend.get_outreach(sent)["status"] == OutreachStatus.REPLIED
    assert backend.get_outreach(sent)["replied_at"] is not None
    assert backend.get_outreach(draft)["status"] == OutreachStatus.DRAFT
    assert backend.mark_outreach_replied([]) == []


def test_outreach_followups_due_once_and_never_after_reply(backend):
    original = _draft(backend)
    _send(backend, original)
    replied = _draft(backend, to_email="raj@contractco.com")
    _send(backend, replied)
    backend.mark_outreach_replied(["raj@contractco.com"])

    cutoff = _iso(timedelta(days=1))
    due = [r["id"] for r in backend.list_followups_due(cutoff)]
    assert original in due and replied not in due
    # Not due yet when the cutoff is before it was sent.
    assert original not in [r["id"] for r in backend.list_followups_due(_iso(-timedelta(days=1)))]

    _draft(backend, parent_id=original)  # the follow-up now exists
    assert original not in [r["id"] for r in backend.list_followups_due(cutoff)]
