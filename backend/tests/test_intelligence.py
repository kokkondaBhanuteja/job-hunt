"""Tests for Career Intelligence Engine: explain_score + skill_gap (stub LLM)."""
from __future__ import annotations

import json

from job_hunt import services
from job_hunt.enums import LearningKind
from job_hunt.services import intelligence
from job_hunt.storage import repo

# ---------- helpers ----------

_STUB_EXPLAIN = {
    "matched": [{"requirement": "Python", "evidence": "3y backend"}],
    "missing": [{"requirement": "Kubernetes", "why_it_matters": "infra role"}],
    "suggestions": ["Learn k8s basics"],
}


def _seed_scored_job(db, h: str = "ei1") -> int:
    jid = db.insert_job_if_new(
        dedup_hash=h, source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="remote",
        description="Python Kubernetes microservices.",
        apply_url="https://example.com/apply", posted_date=None,
    )
    vid = db.upsert_resume_variant(
        slug="backend-py",
        source_path="/resumes/backend.tex",
        parsed={"headline": "Python dev", "skills": {"backend": ["Python", "Django"]},
                "experience": [], "projects": []},
        tags=[],
    )
    db.write_score(job_id=jid, variant_id=vid, fit_score=78, reasoning="solid python fit")
    return jid


# ---------- explain_score ----------


def test_explain_score_returns_breakdown(tmp_db, monkeypatch):
    """explain_score should call the LLM and return matched/missing/suggestions."""
    jid = _seed_scored_job(tmp_db)
    monkeypatch.setattr(intelligence, "chat_json", lambda *a, **k: _STUB_EXPLAIN)

    result = services.explain_score(jid)

    assert result["job_id"] == jid
    assert result["fit_score"] == 78
    assert result["matched"][0]["requirement"] == "Python"
    assert result["missing"][0]["requirement"] == "Kubernetes"
    assert result["suggestions"] == ["Learn k8s basics"]


def test_explain_score_caches_result(tmp_db, monkeypatch):
    """Second call must return cached result without calling the LLM."""
    jid = _seed_scored_job(tmp_db, h="ei2")
    call_count = {"n": 0}

    def counting_stub(*a, **k):
        call_count["n"] += 1
        return _STUB_EXPLAIN

    monkeypatch.setattr(intelligence, "chat_json", counting_stub)
    services.explain_score(jid)
    assert call_count["n"] == 1

    # replace with a stub that raises — cached path must not reach it
    def must_not_call(*a, **k):
        raise RuntimeError("LLM must not be called on a cached result")

    monkeypatch.setattr(intelligence, "chat_json", must_not_call)
    result = services.explain_score(jid)
    assert result["missing"][0]["requirement"] == "Kubernetes"


def test_explain_score_force_bypasses_cache(tmp_db, monkeypatch):
    """force=True must re-call the LLM even when a cached explanation exists."""
    jid = _seed_scored_job(tmp_db, h="ei3")
    call_count = {"n": 0}

    def counting_stub(*a, **k):
        call_count["n"] += 1
        return _STUB_EXPLAIN

    monkeypatch.setattr(intelligence, "chat_json", counting_stub)
    services.explain_score(jid)
    services.explain_score(jid, force=True)
    assert call_count["n"] == 2


def test_explain_score_missing_job(tmp_db, monkeypatch):
    """explain_score with unknown job_id must return {"error": ...}."""
    monkeypatch.setattr(intelligence, "chat_json", lambda *a, **k: _STUB_EXPLAIN)
    result = services.explain_score(99999)
    assert "error" in result
    assert "99999" in result["error"]


def test_explain_score_unscored_job(tmp_db, monkeypatch):
    """explain_score on a job with no score rows must return {"error": ...}."""
    jid = tmp_db.insert_job_if_new(
        dedup_hash="ei4", source="naukri", source_job_id=None, title="Unscored",
        company="X", location=None, description=None,
        apply_url="u", posted_date=None,
    )
    monkeypatch.setattr(intelligence, "chat_json", lambda *a, **k: _STUB_EXPLAIN)
    result = services.explain_score(jid)
    assert "error" in result
    assert "score" in result["error"].lower()


# ---------- skill_gap ----------


def _seed_explanation_learning(db, job_id: int, missing_reqs: list[str]) -> None:
    payload = {
        "matched": [],
        "missing": [{"requirement": r, "why_it_matters": "matters"} for r in missing_reqs],
        "suggestions": [],
    }
    db.save_learning(
        job_id=job_id, variant_id=None, kind=LearningKind.EXPLANATION, payload=payload
    )


def _seed_rejection_learning(db, job_id: int, keywords: list[str]) -> None:
    payload = {"missing_keywords": keywords, "summary": "needs improvement"}
    db.save_learning(
        job_id=job_id, variant_id=None, kind=LearningKind.REJECTION, payload=payload
    )


def test_skill_gap_aggregates_both_kinds(tmp_db):
    """skill_gap must count Kubernetes from both EXPLANATION and REJECTION learnings."""
    j1 = _seed_scored_job(tmp_db, h="sg1")
    j2 = _seed_scored_job(tmp_db, h="sg2")
    _seed_explanation_learning(tmp_db, j1, ["Kubernetes", "Terraform"])
    _seed_rejection_learning(tmp_db, j2, ["kubernetes", "docker"])

    result = services.skill_gap(limit=10)

    gap_map = {g["skill"]: g["count"] for g in result["gaps"]}
    assert gap_map["kubernetes"] == 2   # normalized lowercase from both rows
    assert gap_map["terraform"] == 1
    assert gap_map["docker"] == 1
    assert result["considered"] == 2    # 1 EXPLANATION row + 1 REJECTION row


def test_skill_gap_empty_db(tmp_db):
    """skill_gap on an empty DB must return gaps=[] and considered=0."""
    result = services.skill_gap()
    assert result == {"gaps": [], "considered": 0}


def test_skill_gap_respects_limit(tmp_db):
    """skill_gap(limit=1) must return at most 1 gap."""
    j1 = _seed_scored_job(tmp_db, h="sg3")
    _seed_explanation_learning(tmp_db, j1, ["Kubernetes", "Terraform", "Go"])

    result = services.skill_gap(limit=1)
    assert len(result["gaps"]) == 1


def test_explanation_learning_stored_correctly(tmp_db, monkeypatch):
    """explain_score must store a LearningKind.EXPLANATION row in the learnings table."""
    jid = _seed_scored_job(tmp_db, h="sg4")
    monkeypatch.setattr(intelligence, "chat_json", lambda *a, **k: _STUB_EXPLAIN)

    services.explain_score(jid)

    learnings = repo.list_learnings_for_job(jid)
    explanation_rows = [r for r in learnings if r["kind"] == LearningKind.EXPLANATION]
    assert len(explanation_rows) == 1
    payload = json.loads(explanation_rows[0]["payload"])
    assert payload["missing"][0]["requirement"] == "Kubernetes"
