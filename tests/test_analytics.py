"""Tests for the interview-stage pipeline + analytics dashboard."""
from __future__ import annotations

from job_hunt import services
from job_hunt.enums import ApplicationStage
from job_hunt.storage import repo


def _applied_job(db):
    jid = db.insert_job_if_new(
        dedup_hash="an1", source="remoteok", source_job_id=None, title="BE", company="Acme",
        location="remote", description="d", apply_url="u", posted_date=None,
    )
    db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    services.log_application(jid, "v", "cover", status="applied")
    return jid


def test_new_application_starts_at_applied_stage(tmp_db):
    jid = _applied_job(tmp_db)
    with tmp_db.connect() as conn:
        stage = conn.execute("SELECT stage FROM applications WHERE job_id=?", (jid,)).fetchone()[0]
    assert stage == ApplicationStage.APPLIED


def test_advance_stage(tmp_db):
    jid = _applied_job(tmp_db)
    assert services.advance_stage(jid, "interview")["ok"] is True
    with tmp_db.connect() as conn:
        stage = conn.execute("SELECT stage FROM applications WHERE job_id=?", (jid,)).fetchone()[0]
    assert stage == "interview"


def test_advance_stage_rejects_bad_value(tmp_db):
    jid = _applied_job(tmp_db)
    assert "error" in services.advance_stage(jid, "not-a-stage")


def test_dashboard_shape_and_funnel(tmp_db):
    jid = _applied_job(tmp_db)
    services.advance_stage(jid, "interview")
    repo.write_llm_call(
        task="scoring", provider="stub", model="m", prompt="p", response="r",
        prompt_tokens=10, completion_tokens=5, cost=0.02,
    )

    d = services.dashboard()
    assert {"jobs_by_state", "funnel", "llm_cost", "llm_by_task", "source_effectiveness"} <= set(d)
    funnel = {row["stage"]: row["n"] for row in d["funnel"]}
    assert funnel.get("interview") == 1
    assert d["llm_cost"]["calls"] >= 1
    assert d["llm_cost"]["tokens"] == 15
