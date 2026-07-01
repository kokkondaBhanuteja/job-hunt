"""Tests for the Apply subsystem: ATS detection + AI pre-submit reviewer."""
from __future__ import annotations

import pytest

from job_hunt import services
from job_hunt.apply import reviewer
from job_hunt.apply.ats import detect_ats
from job_hunt.enums import ATSPlatform


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://boards.greenhouse.io/acme/jobs/123", ATSPlatform.GREENHOUSE),
        ("https://jobs.lever.co/acme/abc", ATSPlatform.LEVER),
        ("https://acme.wd1.myworkdayjobs.com/careers", ATSPlatform.WORKDAY),
        ("https://jobs.ashbyhq.com/acme/x", ATSPlatform.ASHBY),
        ("https://careers.smartrecruiters.com/Acme/123", ATSPlatform.SMARTRECRUITERS),
        ("https://acme.icims.com/jobs/1", ATSPlatform.ICIMS),
        ("https://www.naukri.com/job-listings-x", ATSPlatform.NAUKRI),
        ("https://remoteok.com/l/1", ATSPlatform.REMOTEOK),
        ("https://acme.com/careers/1", ATSPlatform.UNKNOWN),
        (None, ATSPlatform.UNKNOWN),
    ],
)
def test_detect_ats(url, expected):
    assert detect_ats(url) == expected


def _seed_scored_job(db):
    jid = db.insert_job_if_new(
        dedup_hash="a1", source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="blr", description="NestJS, AWS, Postgres.",
        apply_url="https://jobs.lever.co/acme/1", posted_date=None,
    )
    vid = db.upsert_resume_variant(
        slug="backend-node", source_path="/x", parsed={"headline": "Backend"}, tags=[]
    )
    db.write_score(job_id=jid, variant_id=vid, fit_score=88, reasoning="strong")
    return jid


def test_review_application_returns_ats_variant_and_verdict(tmp_db, monkeypatch):
    jid = _seed_scored_job(tmp_db)
    monkeypatch.setattr(
        reviewer, "chat_json",
        lambda *a, **k: {"ready": False, "issues": [
            {"severity": "blocker", "field": "cover_letter", "message": "empty"}
        ]},
    )

    result = services.review_application(jid, cover_letter="", answers={})
    assert result["job_id"] == jid
    assert result["ats"] == ATSPlatform.LEVER
    assert result["variant"] == "backend-node"
    assert result["ready"] is False
    assert result["issues"][0]["severity"] == "blocker"


def test_review_application_missing_job(tmp_db):
    assert "error" in services.review_application(9999)
