"""Tests for the apply subsystem: checkpoint/resume + package assembly + snapshot."""
from __future__ import annotations

import pytest

from job_hunt import services
from job_hunt.apply.checkpoint import run_resumable
from job_hunt.apply import reviewer
from job_hunt.storage import repo


def _job(db, h="ap1"):
    return db.insert_job_if_new(
        dedup_hash=h, source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="blr", description="NestJS.", apply_url="https://x/1", posted_date=None,
    )


# ---------- checkpoint / resume ----------


def test_run_resumable_happy_path(tmp_db):
    jid = _job(tmp_db)

    def execute(step, data):
        data.setdefault("done", []).append(step)
        return data

    result = run_resumable(jid, ["page1", "page2", "page3"], execute)
    assert result["done"] == ["page1", "page2", "page3"]
    assert repo.get_checkpoint(jid) is None  # cleared on completion


def test_run_resumable_resumes_after_a_crash(tmp_db):
    jid = _job(tmp_db)

    def flaky(step, data):
        if step == "page2":
            raise RuntimeError("browser crashed")
        data.setdefault("done", []).append(step)
        return data

    with pytest.raises(RuntimeError):
        run_resumable(jid, ["page1", "page2", "page3"], flaky)

    # page1 committed; checkpoint stuck at step 0.
    ck = repo.get_checkpoint(jid)
    assert ck is not None and ck["step"] == 0

    # Re-run with a working executor → resumes at page2, keeps page1.
    def ok(step, data):
        data.setdefault("done", []).append(step)
        return data

    result = run_resumable(jid, ["page1", "page2", "page3"], ok)
    assert result["done"] == ["page1", "page2", "page3"]
    assert repo.get_checkpoint(jid) is None


# ---------- package assembly + snapshot ----------


def test_prepare_application_assembles_package_and_reviews(tmp_db, monkeypatch):
    jid = _job(tmp_db)
    vid = tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"headline": "BE"}, tags=[])
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=88, reasoning="ok")
    tmp_db.save_tailored_resume(job_id=jid, variant_id=vid, content="# Tailored")
    services.add_answer_template("Why do you want to join?", "I love backend systems.")
    monkeypatch.setattr(reviewer, "chat_json", lambda *a, **k: {"ready": True, "issues": []})

    result = services.prepare_application(jid, ["Why do you want to join this company?"])
    assert result["ready"] is True
    assert result["package"]["resume"] == "# Tailored"
    assert result["package"]["answers"][0]["answer"] == "I love backend systems."


def test_record_submitted_resume_snapshots(tmp_db):
    jid = _job(tmp_db)
    vid = tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=80, reasoning="ok")
    tmp_db.save_tailored_resume(job_id=jid, variant_id=vid, content="# Sent Resume")

    out = services.record_submitted_resume(jid)
    assert out["submitted_resume_id"] > 0
    with tmp_db.connect() as conn:
        row = conn.execute("SELECT content FROM submitted_resumes WHERE job_id=?", (jid,)).fetchone()
    assert row["content"] == "# Sent Resume"
