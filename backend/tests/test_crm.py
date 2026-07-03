"""Tests for the recruiter CRM (contacts) + outreach drafting."""
from __future__ import annotations

from job_hunt import services
from job_hunt.draft import outreach as outreach_mod
from job_hunt.enums import DraftKind


def test_add_and_list_contacts(tmp_db):
    services.add_contact(company="Acme", name="Ravi", role="Recruiter", email_guess="ravi@acme.com")
    services.add_contact(company="Beta", name="Sam")

    assert len(services.list_contacts()) == 2
    acme = services.list_contacts("Acme")
    assert len(acme) == 1 and acme[0]["email_guess"] == "ravi@acme.com"


def test_add_contact_upserts_on_company_name(tmp_db):
    services.add_contact(company="Acme", name="Ravi", role="Recruiter")
    services.add_contact(company="Acme", name="Ravi", role="Sr. Recruiter", notes="warm")

    contacts = services.list_contacts("Acme")
    assert len(contacts) == 1
    assert contacts[0]["role"] == "Sr. Recruiter" and contacts[0]["notes"] == "warm"


def test_draft_outreach_saves_outreach_draft(tmp_db, monkeypatch):
    jid = tmp_db.insert_job_if_new(
        dedup_hash="o1", source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="blr", description="NestJS.", apply_url="u", posted_date=None,
    )
    monkeypatch.setattr(outreach_mod, "chat", lambda *a, **k: "Hi Ravi, I build NestJS APIs...")

    result = services.draft_outreach_for_job(jid, contact_name="Ravi")
    assert result["kind"] == DraftKind.OUTREACH
    drafts = services.list_drafts(jid)
    assert len(drafts) == 1 and drafts[0]["kind"] == "outreach"
