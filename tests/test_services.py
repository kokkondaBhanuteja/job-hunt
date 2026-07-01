"""Tests for the services layer + enum-derived schema constraints."""
from __future__ import annotations

import sqlite3

import pytest

from job_hunt import services
from job_hunt.enums import ApplicationOutcome, JobState


def _seed(db):
    job_id = db.insert_job_if_new(
        dedup_hash="h", source="naukri", source_job_id=None, title="BE",
        company="Acme", location="blr", description="d", apply_url="u", posted_date=None,
    )
    db.upsert_resume_variant(slug="backend-node", source_path="/x", parsed={"h": 1}, tags=[])
    return job_id


def test_log_application_applied_sets_state_and_records(tmp_db):
    job_id = _seed(tmp_db)
    out = services.log_application(job_id, "backend-node", "cover", status=ApplicationOutcome.APPLIED)
    assert out["ok"] is True

    job = tmp_db.get_job(job_id)
    assert job["state"] == JobState.APPLIED  # jobs.state is the lifecycle authority now
    with tmp_db.connect() as conn:
        app = conn.execute("SELECT * FROM applications WHERE job_id=?", (job_id,)).fetchone()
    assert app is not None and app["cover_letter"] == "cover"


def test_log_application_rejects_unknown_status(tmp_db):
    job_id = _seed(tmp_db)
    out = services.log_application(job_id, "backend-node", "x", status="bogus")
    assert "error" in out


def test_log_application_rejects_unknown_variant(tmp_db):
    job_id = _seed(tmp_db)
    out = services.log_application(job_id, "no-such-variant", "x")
    assert "error" in out


def test_schema_check_constraint_rejects_invalid_status(tmp_db):
    """The enum-derived CHECK constraint must actually be enforced by SQLite."""
    job_id = _seed(tmp_db)
    with pytest.raises(sqlite3.IntegrityError):
        tmp_db.set_job_status(job_id, "not-a-real-status")


def test_get_job_includes_confidence_in_scores(tmp_db):
    job_id = _seed(tmp_db)
    vid = tmp_db.find_variant_id_by_slug("backend-node")
    tmp_db.write_score(job_id=job_id, variant_id=vid, fit_score=90, reasoning="r", confidence=55)

    out = services.get_job(job_id)
    assert out["job"]["id"] == job_id
    assert out["scores"][0]["confidence"] == 55
