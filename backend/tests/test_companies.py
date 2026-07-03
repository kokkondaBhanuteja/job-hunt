"""Tests for company cache + memory/history."""
from __future__ import annotations

from job_hunt import services


def test_company_history_counts_roles_and_applications(tmp_db):
    j1 = tmp_db.insert_job_if_new(
        dedup_hash="ch1", source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="blr", description="d", apply_url="u1", posted_date=None,
    )
    tmp_db.insert_job_if_new(
        dedup_hash="ch2", source="naukri", source_job_id=None, title="Platform Engineer",
        company="Acme", location="blr", description="d", apply_url="u2", posted_date=None,
    )
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    services.log_application(j1, "v", "cover")

    hist = services.company_history("Acme")
    assert hist["roles_seen"] == 2
    assert hist["applications"] == 1
    assert hist["company"] == "Acme"


def test_company_history_empty_for_unknown(tmp_db):
    hist = services.company_history("Nobody")
    assert hist["roles_seen"] == 0 and hist["applications"] == 0
