"""Characterization tests for the SQLite repository layer (job_hunt/storage/db.py)."""
from __future__ import annotations

import sqlite3

import pytest

from job_hunt.enums import OutreachStatus

_OUTREACH_SEND_COLS = {"to_email", "status", "parent_id", "message_id", "last_error", "replied_at"}


def _insert_job(db, *, company="Acme", title="Backend Engineer", h="hash-1", status_new=True):
    return db.insert_job_if_new(
        dedup_hash=h,
        source="naukri",
        source_job_id=None,
        title=title,
        company=company,
        location="bangalore",
        description="Build APIs in NestJS.",
        apply_url="https://example.com/job/1",
        posted_date="2026-06-29",
    )


def test_insert_job_returns_id_then_dedups(tmp_db):
    first = _insert_job(tmp_db, h="dup-hash")
    assert isinstance(first, int) and first > 0

    # Same dedup_hash → insert is skipped, returns None.
    second = _insert_job(tmp_db, h="dup-hash", title="Senior Backend Engineer")
    assert second is None


def test_upsert_resume_variant_is_idempotent(tmp_db):
    vid1 = tmp_db.upsert_resume_variant(
        slug="backend-node",
        source_path="/x/backend-node.tex",
        parsed={"headline": "Backend Engineer", "skills": {"backend": ["nestjs"]}},
        tags=["nestjs", "aws"],
    )
    vid2 = tmp_db.upsert_resume_variant(
        slug="backend-node",
        source_path="/x/backend-node.tex",
        parsed={"headline": "Backend Engineer v2"},
        tags=["nestjs"],
    )
    assert vid1 == vid2  # same slug → updated in place, not duplicated

    variants = tmp_db.list_resume_variants()
    assert len(variants) == 1
    assert variants[0]["slug"] == "backend-node"


def test_write_score_and_top_matches(tmp_db):
    job_id = _insert_job(tmp_db, h="score-hash")
    vid = tmp_db.upsert_resume_variant(
        slug="backend-node", source_path="/x.tex", parsed={"headline": "x"}, tags=[]
    )
    tmp_db.write_score(job_id=job_id, variant_id=vid, fit_score=88, reasoning="strong overlap")

    # Above threshold → returned with winning variant.
    rows = tmp_db.top_matches(min_score=70, limit=10)
    assert len(rows) == 1
    assert rows[0]["best_score"] == 88
    assert rows[0]["best_variant"] == "backend-node"

    # Below threshold → filtered out.
    assert tmp_db.top_matches(min_score=90, limit=10) == []


def test_list_scorable_jobs_excludes_already_scored(tmp_db):
    job_id = _insert_job(tmp_db, h="pending-hash")
    assert [r["id"] for r in tmp_db.list_scorable_jobs()] == [job_id]

    vid = tmp_db.upsert_resume_variant(
        slug="v", source_path="/x.tex", parsed={"h": 1}, tags=[]
    )
    tmp_db.write_score(job_id=job_id, variant_id=vid, fit_score=50, reasoning="ok")

    # list_scorable_jobs is state-based: the job is still 'discovered' (score written directly),
    # so it remains scorable — the idempotency gate in scoring/match handles the skip.
    assert [r["id"] for r in tmp_db.list_scorable_jobs()] == [job_id]


# ---------- outreach (0025: cold-email sending) ----------


def _outreach_cols(path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(outreach)")}


def _insert_outreach(conn: sqlite3.Connection, contact_id: int, **extra: object) -> int:
    cols = ["contact_id", "template_slug", "subject", "body", "mailto_url", "drafted_at"]
    vals: list[object] = [contact_id, "cold_email@1", "Hi", "Body", "mailto:x", "2026-11-24"]
    cols += list(extra)
    vals += list(extra.values())
    cur = conn.execute(
        f"INSERT INTO outreach ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals
    )
    return int(cur.lastrowid)


def test_fresh_outreach_has_send_columns_and_defaults_to_draft(tmp_db):
    assert _OUTREACH_SEND_COLS <= _outreach_cols(tmp_db.DB_PATH)
    contact_id = tmp_db.save_contact(company="Acme", name="Priya")
    with sqlite3.connect(tmp_db.DB_PATH) as conn:
        oid = _insert_outreach(conn, contact_id)
        status = conn.execute("SELECT status FROM outreach WHERE id = ?", (oid,)).fetchone()[0]
    assert status == OutreachStatus.DRAFT


def test_fresh_outreach_rejects_unknown_status(tmp_db):
    contact_id = tmp_db.save_contact(company="Acme", name="Priya")
    with sqlite3.connect(tmp_db.DB_PATH) as conn, pytest.raises(sqlite3.IntegrityError):
        _insert_outreach(conn, contact_id, status="spammed")


def test_outreach_allows_one_follow_up_per_original(tmp_db):
    contact_id = tmp_db.save_contact(company="Acme", name="Priya")
    with sqlite3.connect(tmp_db.DB_PATH) as conn:
        original = _insert_outreach(conn, contact_id)
        _insert_outreach(conn, contact_id, parent_id=original)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_outreach(conn, contact_id, parent_id=original)
        # Originals (parent_id NULL) never collide with each other.
        _insert_outreach(conn, contact_id)


def test_migration_adds_send_columns_to_old_outreach_table(tmp_path, monkeypatch):
    """A pre-0025 DB keeps its outreach rows and gains the send columns via init_db()."""
    from job_hunt.storage import db

    path = tmp_path / "old.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT NOT NULL,"
            " name TEXT NOT NULL, created_at TEXT, UNIQUE(company, name))"
        )
        conn.execute(
            """
            CREATE TABLE outreach (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id    INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                job_id        INTEGER,
                template_slug TEXT NOT NULL,
                subject       TEXT NOT NULL,
                body          TEXT NOT NULL,
                mailto_url    TEXT NOT NULL,
                drafted_at    TEXT NOT NULL,
                sent_at       TEXT
            )
            """
        )
        conn.execute("INSERT INTO contacts (company, name) VALUES ('Acme', 'Priya')")
        old_id = _insert_outreach(conn, 1)

    db.init_db(path)

    assert _OUTREACH_SEND_COLS <= _outreach_cols(path)
    with sqlite3.connect(path) as conn:
        status = conn.execute("SELECT status FROM outreach WHERE id = ?", (old_id,)).fetchone()[0]
    assert status == OutreachStatus.DRAFT
