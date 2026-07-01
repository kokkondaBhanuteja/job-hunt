"""D5/D4: end-to-end HTTP journey through the management surface + durability/health checks."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from job_hunt.api import app as app_module
from job_hunt.api.app import app
from job_hunt.apply import reviewer
from job_hunt.enums import JobState
from job_hunt.services import drafting
from job_hunt.states import transition_job
from job_hunt.storage import repo

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    return TestClient(app)


def _scored_job(tmp_db):
    jid = tmp_db.insert_job_if_new(
        dedup_hash="e2e", source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="blr", description="NestJS", apply_url="u", posted_date=None,
        emit_discovered=True,
    )
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    tmp_db.write_score(job_id=jid, variant_id=1, fit_score=88, reasoning="ok")
    transition_job(jid, JobState.SCORED)
    return jid


def test_management_journey_end_to_end(client, tmp_db, monkeypatch):
    jid = _scored_job(tmp_db)
    monkeypatch.setattr(drafting, "tailor_resume", lambda **k: "# tailored")
    monkeypatch.setattr(drafting, "generate_cover_letter", lambda **k: "Dear team,")
    monkeypatch.setattr(reviewer, "chat_json", lambda *a, **k: {"ready": True, "issues": []})

    assert any(j["id"] == jid for j in client.get("/api/board", headers=AUTH).json())

    assert client.post(f"/api/jobs/{jid}/tailor", headers=AUTH).status_code == 200
    assert client.post(f"/api/jobs/{jid}/cover", headers=AUTH).status_code == 200

    prep = client.post(f"/api/jobs/{jid}/prepare", headers=AUTH, json=[])
    assert prep.status_code == 200 and prep.json()["ready"] is True

    applied = client.post("/api/applications", headers=AUTH,
                          json={"job_id": jid, "variant_slug": "v", "cover_letter": "x"})
    assert applied.status_code == 200

    staged = client.patch(f"/api/applications/{jid}/stage", headers=AUTH, json={"stage": "interview"})
    assert staged.status_code == 200

    assert client.get(f"/api/jobs/{jid}", headers=AUTH).json()["job"]["state"] == "interview"


def test_score_trigger_creates_a_run_row(client, tmp_db, monkeypatch):
    tmp_db.insert_job_if_new(
        dedup_hash="s1", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="u", posted_date=None, emit_discovered=True,
    )
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    from job_hunt.scoring import match
    monkeypatch.setattr(match, "chat_json", lambda *a, **k: {"fit_score": 70, "reasoning": "ok"})

    assert client.post("/api/score", headers=AUTH).status_code == 202
    runs = client.get("/api/runs", headers=AUTH).json()  # TestClient runs the bg task inline
    assert any("score" in (r.get("sources") or "") for r in runs)


def test_health_reports_degraded_when_db_down(client, monkeypatch):
    monkeypatch.setattr(app_module, "_db_ok", lambda: False)
    body = client.get("/health").json()
    assert body["status"] == "degraded" and body["db_ok"] is False


def test_reap_stale_runs(tmp_db):
    rid = tmp_db.create_run(["naukri"])
    tmp_db.start_run(rid)
    with tmp_db.connect() as conn:  # force an ancient heartbeat
        conn.execute("UPDATE runs SET heartbeat_at = ? WHERE id = ?",
                     ("2020-01-01T00:00:00+00:00", rid))

    assert tmp_db.reap_stale_runs(max_age_s=60) == 1
    assert repo.get_run(rid)["status"] == "failed"

    fresh = tmp_db.create_run(["naukri"])
    tmp_db.start_run(fresh)
    assert tmp_db.reap_stale_runs(max_age_s=3600) == 0  # fresh heartbeat is not reaped
