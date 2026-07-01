"""Tests for the learning loop: rejection gaps + variant performance (stub LLM)."""
from __future__ import annotations

from job_hunt import services
from job_hunt.enums import LearningKind
from job_hunt.learn import analyze
from job_hunt.storage import repo


def _scored_job(db, h="l1"):
    jid = db.insert_job_if_new(
        dedup_hash=h, source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="Kafka, Spring Boot, AWS.", apply_url="u", posted_date=None,
    )
    vid = db.upsert_resume_variant(slug="backend-java", source_path="/x", parsed={"h": 1}, tags=[])
    db.write_score(job_id=jid, variant_id=vid, fit_score=70, reasoning="ok")
    return jid


def test_learn_from_rejection_stores_gap(tmp_db, monkeypatch):
    jid = _scored_job(tmp_db)
    monkeypatch.setattr(
        analyze, "chat_json",
        lambda *a, **k: {"missing_keywords": ["kafka"], "summary": "emphasize Kafka next time"},
    )

    result = services.learn_from_rejection(jid)
    assert result["missing_keywords"] == ["kafka"]

    learnings = repo.list_learnings_for_job(jid)
    assert len(learnings) == 1 and learnings[0]["kind"] == LearningKind.REJECTION


def test_variant_performance_aggregates_outcomes(tmp_db):
    j1 = _scored_job(tmp_db, h="l2")
    j2 = _scored_job(tmp_db, h="l3")
    services.log_application(j1, "backend-java", "cover")
    services.log_application(j2, "backend-java", "cover")
    services.advance_stage(j1, "interview")
    services.advance_stage(j2, "rejected")

    perf = {r["variant"]: r for r in services.variant_performance()}
    row = perf["backend-java"]
    assert row["applications"] == 2
    assert row["interviews"] == 1
    assert row["rejections"] == 1


def test_dashboard_includes_variant_performance(tmp_db):
    assert "variant_performance" in services.dashboard()
