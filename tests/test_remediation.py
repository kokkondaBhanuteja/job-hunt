"""Regression tests for the remediation pass (atomic outbox, top_matches, per-job scoring)."""
from __future__ import annotations

import pytest

from job_hunt import services, states
from job_hunt.enums import JobState
from job_hunt.scoring import match
from job_hunt.storage import db, repo


def _job(tmp_db, h="r1"):
    return tmp_db.insert_job_if_new(
        dedup_hash=h, source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="blr", description="NestJS, Kafka.", apply_url="u", posted_date=None,
    )


# ---------- R1.1 atomic transition (finding #1) ----------


def test_transition_is_all_or_nothing(tmp_db, monkeypatch):
    jid = _job(tmp_db)
    # Force the event-insert inside apply_transition to fail → the whole tx must roll back.
    monkeypatch.setattr(db, "_to_json", lambda v: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        states.transition_job(jid, JobState.SCORED)  # SCORED emits JOB_SCORED → uses _to_json

    assert repo.get_job_state(jid) == JobState.DISCOVERED       # state NOT changed
    with tmp_db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM job_transitions WHERE job_id=?", (jid,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 0


def test_transition_persists_all_three_together(tmp_db):
    jid = _job(tmp_db)
    states.transition_job(jid, JobState.SCORED, reason="x")
    assert repo.get_job_state(jid) == JobState.SCORED
    with tmp_db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM job_transitions WHERE job_id=?", (jid,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM events WHERE type='job.scored'").fetchone()[0] == 1


# ---------- R1.2 top_matches winning variant (finding #5) ----------


def test_top_matches_one_row_per_job_with_winning_variant(tmp_db):
    jid = _job(tmp_db)
    va = tmp_db.upsert_resume_variant(slug="a", source_path="/a", parsed={"h": 1}, tags=[])
    vb = tmp_db.upsert_resume_variant(slug="b", source_path="/b", parsed={"h": 1}, tags=[])
    tmp_db.write_score(job_id=jid, variant_id=va, fit_score=70, reasoning="ok")
    tmp_db.write_score(job_id=jid, variant_id=vb, fit_score=90, reasoning="better")

    rows = tmp_db.top_matches(min_score=60, limit=10)
    assert len(rows) == 1                       # exactly one row per job (not one per variant)
    assert rows[0]["best_variant"] == "b"       # the higher-scoring variant
    assert rows[0]["best_score"] == 90


# ---------- R1.3 per-job scoring (finding #3) ----------


def test_score_job_scores_only_that_job(tmp_db, monkeypatch):
    j1 = _job(tmp_db, h="sj1")
    j2 = _job(tmp_db, h="sj2")
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    monkeypatch.setattr(match, "chat_json", lambda *a, **k: {"fit_score": 80, "reasoning": "ok"})

    result = match.score_job(j1)
    assert result["jobs_scored"] == 1

    with tmp_db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM scores WHERE job_id=?", (j1,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM scores WHERE job_id=?", (j2,)).fetchone()[0] == 0
    assert repo.get_job_state(j1) == JobState.SCORED


# ---------- R2 unified lifecycle: jobs.state follows application outcomes (finding #4) ----------


def test_log_application_moves_job_state(tmp_db):
    jid = _job(tmp_db)
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])

    services.log_application(jid, "v", "cover", status="applied")
    assert repo.get_job_state(jid) == JobState.APPLIED

    j2 = _job(tmp_db, h="r2-skip")
    services.log_application(j2, "v", "", status="skipped")
    assert repo.get_job_state(j2) == JobState.ARCHIVED


def test_advance_stage_moves_job_state_and_funnel(tmp_db):
    jid = _job(tmp_db)
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    services.log_application(jid, "v", "cover")

    services.advance_stage(jid, "interview")
    assert repo.get_job_state(jid) == JobState.INTERVIEW      # jobs.state moved (board)
    with tmp_db.connect() as conn:                            # applications.stage moved (funnel)
        assert conn.execute("SELECT stage FROM applications WHERE job_id=?", (jid,)).fetchone()[0] == "interview"


# ---------- R4 hardening (findings #16, #13) ----------


def test_enrich_is_a_source_capability(tmp_db):
    from job_hunt import plugins
    from job_hunt.services.enrichment import source_enrich_fetchers

    assert hasattr(plugins.get_source("naukri"), "enrich")      # snippet source → enriches
    assert not hasattr(plugins.get_source("remoteok"), "enrich")  # API ships full JD → no enrich
    assert set(source_enrich_fetchers().keys()) == {"naukri"}


def test_raw_select_rejects_mutations():
    with pytest.raises(ValueError):
        repo.raw_select("DELETE FROM jobs")
    with pytest.raises(ValueError):
        repo.raw_select("UPDATE jobs SET state='x'")


# ---------- A4: atomic first lifecycle hop (no orphaned jobs) ----------


def test_insert_emits_discovered_atomically(tmp_db):
    jid = tmp_db.insert_job_if_new(
        dedup_hash="a4", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="u", posted_date=None, emit_discovered=True,
    )
    with tmp_db.connect() as conn:
        events = conn.execute(
            "SELECT count(*) AS c FROM events WHERE type='job.discovered'"
        ).fetchone()["c"]
        trans = conn.execute(
            "SELECT count(*) AS c FROM job_transitions WHERE job_id=? AND to_state='discovered'",
            (jid,),
        ).fetchone()["c"]
    assert events == 1 and trans == 1  # row + event committed together
    assert any(e["type"] == "job.discovered" for e in tmp_db.fetch_unprocessed_events())


def test_scores_meta_for_jobs_groups_by_job(tmp_db):
    j1 = _job(tmp_db, h="m1")
    j2 = _job(tmp_db, h="m2")
    vid = tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    tmp_db.write_score(job_id=j1, variant_id=vid, fit_score=70, reasoning="a")
    tmp_db.write_score(job_id=j2, variant_id=vid, fit_score=80, reasoning="b")

    meta = tmp_db.scores_meta_for_jobs([j1, j2, 9999])
    assert set(meta.keys()) == {j1, j2}          # 9999 has no scores → absent
    assert len(meta[j1]) == 1 and int(meta[j1][0]["variant_id"]) == vid
    assert tmp_db.scores_meta_for_jobs([]) == {}


def test_insert_without_flag_emits_nothing(tmp_db):
    tmp_db.insert_job_if_new(
        dedup_hash="a4b", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="u", posted_date=None,
    )
    with tmp_db.connect() as conn:
        assert conn.execute("SELECT count(*) AS c FROM events").fetchone()["c"] == 0
