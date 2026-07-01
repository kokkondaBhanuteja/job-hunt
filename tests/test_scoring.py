"""Characterization tests for scoring orchestration with a STUB LLM (no Ollama)."""
from __future__ import annotations

import pytest

from job_hunt.scoring import match


def _seed_job(db, h="s-hash"):
    return db.insert_job_if_new(
        dedup_hash=h,
        source="naukri",
        source_job_id=None,
        title="Backend Engineer",
        company="Acme",
        location="bangalore",
        description="NestJS, AWS, Postgres.",
        apply_url="https://example.com/1",
        posted_date=None,
    )


def test_score_all_pending_writes_one_row_per_job_variant(tmp_db, monkeypatch):
    _seed_job(tmp_db)
    tmp_db.upsert_resume_variant(
        slug="backend-node", source_path="/x.tex",
        parsed={"headline": "Backend", "skills": {"backend": ["nestjs"]}}, tags=["nestjs"],
    )

    # Stub the LLM: scoring must not call Ollama.
    monkeypatch.setattr(
        match, "chat_json", lambda *a, **k: {"fit_score": 77, "reasoning": "stub reasoning"}
    )

    summary = match.score_all_pending()
    assert summary == {"jobs_scored": 1, "score_rows_written": 1}

    rows = tmp_db.top_matches(min_score=70, limit=10)
    assert len(rows) == 1
    assert rows[0]["best_score"] == 77
    assert rows[0]["best_variant"] == "backend-node"


def test_score_all_pending_requires_variants(tmp_db, monkeypatch):
    _seed_job(tmp_db)
    monkeypatch.setattr(match, "chat_json", lambda *a, **k: {"fit_score": 1, "reasoning": "x"})
    with pytest.raises(RuntimeError):
        match.score_all_pending()


def _stub(monkeypatch):
    monkeypatch.setattr(
        match, "chat_json", lambda *a, **k: {"fit_score": 77, "reasoning": "stub"}
    )


def test_scoring_is_idempotent(tmp_db, monkeypatch):
    _seed_job(tmp_db)
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    _stub(monkeypatch)

    first = match.score_all_pending()
    assert first == {"jobs_scored": 1, "score_rows_written": 1}

    # Nothing changed → re-run scores nothing (no re-billing).
    second = match.score_all_pending()
    assert second == {"jobs_scored": 0, "score_rows_written": 0}


def test_enrichment_triggers_one_rescore_against_full_jd(tmp_db, monkeypatch):
    jid = _seed_job(tmp_db)
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    _stub(monkeypatch)

    match.score_all_pending()  # scores against the snippet
    with tmp_db.connect() as conn:
        assert conn.execute("SELECT scored_against FROM scores WHERE job_id=?", (jid,)).fetchone()[0] == "snippet"

    # Enrich → full JD differs → exactly one re-score, now against 'full'.
    tmp_db.set_job_enriched(jid, "A much longer full job description with real requirements.")
    summary = match.score_all_pending()
    assert summary == {"jobs_scored": 1, "score_rows_written": 1}
    with tmp_db.connect() as conn:
        assert conn.execute("SELECT scored_against FROM scores WHERE job_id=?", (jid,)).fetchone()[0] == "full"
