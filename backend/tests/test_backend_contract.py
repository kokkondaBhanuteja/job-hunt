"""C1/C2: contract tests run the SAME assertions against BOTH backends, so the 786 lines of
hand-written Postgres SQL are proven to behave identically to SQLite — not just assumed.

Postgres is exercised against the dev DB (gated on reachability) and every row created here is
namespaced (`company='ContractCo'`, slugs `contract-*`) and cleaned up before + after.
"""
from __future__ import annotations

import pytest

from job_hunt.enums import JobState
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
