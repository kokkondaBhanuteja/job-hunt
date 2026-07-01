"""Tests for the FastAPI app (SQLite backend, in-process TestClient)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from job_hunt.api.app import app

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    return TestClient(app)


def test_health_is_open_and_reports_config(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["datastore"] == "sqlite"
    assert "naukri" in body["sources"]


def test_api_requires_token(client):
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/jobs", headers=AUTH).status_code == 200


def test_jobs_empty_then_reflects_data(client, tmp_db):
    assert client.get("/api/jobs", headers=AUTH).json() == []

    jid = tmp_db.insert_job_if_new(
        dedup_hash="h", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="u", posted_date=None,
    )
    vid = tmp_db.upsert_resume_variant(slug="backend-node", source_path="/x", parsed={"h": 1}, tags=[])
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=90, reasoning="r", confidence=70)

    jobs = client.get("/api/jobs?min_score=70", headers=AUTH).json()
    assert len(jobs) == 1 and jobs[0]["best_score"] == 90

    detail = client.get(f"/api/jobs/{jid}", headers=AUTH).json()
    assert detail["job"]["id"] == jid
    assert client.get("/api/jobs/9999", headers=AUTH).status_code == 404


def test_search_profile_crud_via_api(client):
    r = client.post("/api/search-profiles", headers=AUTH,
                    json={"name": "java-blr", "keywords": "java spring", "location": "bangalore", "pages": 2})
    assert r.status_code == 201
    pid = r.json()["id"]

    listing = client.get("/api/search-profiles", headers=AUTH).json()
    assert any(p["name"] == "java-blr" for p in listing)

    patched = client.patch(f"/api/search-profiles/{pid}", headers=AUTH, json={"enabled": False})
    assert patched.json()["enabled"] is False


def test_trigger_score_returns_202(client):
    assert client.post("/api/score", headers=AUTH).status_code == 202


def test_log_application_bad_variant_is_400(client, tmp_db):
    jid = tmp_db.insert_job_if_new(
        dedup_hash="h2", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="u", posted_date=None,
    )
    r = client.post("/api/applications", headers=AUTH,
                    json={"job_id": jid, "variant_slug": "nope", "cover_letter": "x"})
    assert r.status_code == 400
