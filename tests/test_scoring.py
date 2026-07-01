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
