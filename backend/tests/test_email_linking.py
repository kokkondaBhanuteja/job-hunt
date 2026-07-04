"""Tests for email_triage linking: company/job/application FK resolution.

Covers: matching an email to a seeded job by company+role, graceful no-match
when company is unknown, and get_email returning the linked IDs.
"""
from __future__ import annotations

from job_hunt.services import email_triage
from job_hunt.storage import repo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_job(
    db,
    *,
    company: str = "Acme",
    title: str = "Backend Engineer",
    dedup_hash: str = "acme-be-hash",
) -> int:
    return db.insert_job_if_new(
        dedup_hash=dedup_hash,
        source="test",
        source_job_id=None,
        title=title,
        company=company,
        location="remote",
        description="Python backend role.",
        apply_url="https://example.com/jobs/1",
        posted_date=None,
    )


def _upsert_email(
    uid: int,
    message_id: str,
    from_addr: str = "hr@acme.com",
    subject: str = "Interview for Backend Engineer",
    body_text: str = "We'd like to invite you to interview.",
) -> int:
    return repo.upsert_email_message(
        mailbox="INBOX",
        uid=uid,
        message_id=message_id,
        thread_id=None,
        from_addr=from_addr,
        from_name="HR",
        subject=subject,
        received_at=None,
        snippet=None,
        body_text=body_text,
    )


def _stub_llm(monkeypatch, *, company: str, role: str, category: str = "interview_invite") -> None:
    monkeypatch.setattr(
        email_triage,
        "chat_json",
        lambda *a, **k: {
            "is_job_related": True,
            "category": category,
            "company": company,
            "role": role,
            "summary": "Structured by stub.",
        },
    )


# ---------------------------------------------------------------------------
# Matching tests
# ---------------------------------------------------------------------------


def test_link_email_resolves_job_id_for_seeded_job(tmp_db, monkeypatch):
    """When a matching company+role exists in the pipeline, job_id must be set."""
    _seed_job(tmp_db)
    email_id = _upsert_email(uid=10, message_id="link-1")
    _stub_llm(monkeypatch, company="Acme", role="Backend Engineer")

    email_triage.structure_pending()

    result = email_triage.get_email(email_id)
    assert result.get("job_id") is not None, (
        "Expected job_id to be linked for company=Acme, role=Backend Engineer"
    )


def test_link_email_graceful_no_match_unknown_company(tmp_db, monkeypatch):
    """If no history exists for the extracted company, all FK fields stay None."""
    email_id = _upsert_email(
        uid=11,
        message_id="link-2",
        from_addr="hr@nope.com",
        subject="Interview at Nope",
    )
    _stub_llm(monkeypatch, company="Nope", role="Engineer", category="recruiter_outreach")

    email_triage.structure_pending()

    result = email_triage.get_email(email_id)
    assert result.get("job_id") is None, "Unexpected job_id for unknown company"
    assert result.get("company_id") is None, "Unexpected company_id for unknown company"


def test_link_email_no_role_does_not_link_job(tmp_db, monkeypatch):
    """An email with a known company but no role must not link to a job (avoids false positives)."""
    _seed_job(tmp_db)
    email_id = _upsert_email(uid=12, message_id="link-3")

    monkeypatch.setattr(
        email_triage,
        "chat_json",
        lambda *a, **k: {
            "is_job_related": True,
            "category": "recruiter_outreach",
            "company": "Acme",
            # no role key
            "summary": "General outreach from Acme.",
        },
    )

    email_triage.structure_pending()

    result = email_triage.get_email(email_id)
    assert result.get("job_id") is None, "job_id should be None when no role is present"


# ---------------------------------------------------------------------------
# get_email tests
# ---------------------------------------------------------------------------


def test_get_email_returns_dict(tmp_db):
    """get_email must return a plain dict with at least the id field."""
    email_id = _upsert_email(uid=20, message_id="ge-1")
    result = email_triage.get_email(email_id)
    assert isinstance(result, dict)
    assert result["id"] == email_id


def test_get_email_returns_error_for_missing_id(tmp_db):
    """get_email must return {"error": ...} when the row does not exist."""
    result = email_triage.get_email(99999)
    assert "error" in result
