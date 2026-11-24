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


# ---------- cold-email outreach ----------

_DRAFT = {
    "company": "Acme", "contact_name": "Priya Sharma", "to_email": "priya@acme.com",
    "subject": "Backend engineer, NestJS", "body": "Hi Priya,\n\nShort note.\n\nThanks,\nBhanu",
}


@pytest.fixture
def outreach_client(client, tmp_db, monkeypatch):
    tmp_db.set_applicant_profile(fields={"first_name": "Bhanu", "last_name": "Teja"})
    for var in ("EMAIL_SMTP_HOST", "EMAIL_ADDRESS", "EMAIL_APP_PASSWORD", "EMAIL_IMAP_HOST"):
        monkeypatch.delenv(var, raising=False)
    return client


def test_outreach_routes_require_token(outreach_client):
    assert outreach_client.get("/api/outreach").status_code == 401
    assert outreach_client.post("/api/outreach/1/send", json={"confirm": True}).status_code == 401


def test_outreach_create_list_edit_cancel(outreach_client):
    r = outreach_client.post("/api/outreach", json=_DRAFT, headers=AUTH)
    assert r.status_code == 201
    draft = r.json()
    assert draft["status"] == "draft" and draft["warnings"] == []
    assert draft["body"].endswith("-- \nBhanu Teja")

    listed = outreach_client.get("/api/outreach?status=draft", headers=AUTH).json()
    assert [o["id"] for o in listed] == [draft["id"]]
    assert outreach_client.get("/api/outreach?status=spammed", headers=AUTH).status_code == 422

    edited = outreach_client.patch(
        f"/api/outreach/{draft['id']}", json={"subject": "Backend role at Acme"}, headers=AUTH,
    )
    assert edited.status_code == 200 and edited.json()["subject"] == "Backend role at Acme"

    cancelled = outreach_client.post(f"/api/outreach/{draft['id']}/cancel", headers=AUTH)
    assert cancelled.json() == {"id": draft["id"], "status": "cancelled", "sent_at": None}


def test_outreach_errors_map_to_400_and_404(outreach_client):
    bad = outreach_client.post("/api/outreach", json={**_DRAFT, "to_email": "not-an-email"},
                               headers=AUTH)
    assert bad.status_code == 400
    assert outreach_client.post("/api/outreach/999/cancel", headers=AUTH).status_code == 404
    assert outreach_client.patch("/api/outreach/999", json={}, headers=AUTH).status_code == 404


@pytest.mark.parametrize("payload", [{}, {"confirm": False}])
def test_outreach_send_without_confirm_is_refused(outreach_client, payload):
    oid = outreach_client.post("/api/outreach", json=_DRAFT, headers=AUTH).json()["id"]
    r = outreach_client.post(f"/api/outreach/{oid}/send", json=payload, headers=AUTH)
    assert r.status_code == 400 and "confirmation required" in r.text


@pytest.mark.parametrize("confirm", ["yes", "true", 1])
def test_outreach_send_only_accepts_json_true(outreach_client, confirm):
    oid = outreach_client.post("/api/outreach", json=_DRAFT, headers=AUTH).json()["id"]
    r = outreach_client.post(f"/api/outreach/{oid}/send", json={"confirm": confirm}, headers=AUTH)
    assert r.status_code == 422  # StrictBool: no coercion into a send


def test_outreach_send_with_confirm_reaches_the_service(outreach_client):
    oid = outreach_client.post("/api/outreach", json=_DRAFT, headers=AUTH).json()["id"]
    r = outreach_client.post(f"/api/outreach/{oid}/send", json={"confirm": True}, headers=AUTH)
    assert r.status_code == 400 and "smtp not configured" in r.text  # passed the gate
