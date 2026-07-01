"""Tests for drafting: resume tailoring + cover letters (stub LLM)."""
from __future__ import annotations

from job_hunt import services
from job_hunt.draft import cover
from job_hunt.enums import DraftKind
from job_hunt.resume import tailor
from job_hunt.storage import repo


def _scored_job(db):
    jid = db.insert_job_if_new(
        dedup_hash="d1", source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="blr", description="NestJS, AWS, Postgres.",
        apply_url="https://x/1", posted_date=None,
    )
    vid = db.upsert_resume_variant(
        slug="backend-node", source_path="/x", parsed={"headline": "Backend"}, tags=[]
    )
    db.write_score(job_id=jid, variant_id=vid, fit_score=88, reasoning="strong")
    return jid


def test_tailor_for_job_persists(tmp_db, monkeypatch):
    jid = _scored_job(tmp_db)
    monkeypatch.setattr(tailor, "chat", lambda *a, **k: "# Tailored Resume\n- NestJS, AWS")

    result = services.tailor_for_job(jid)
    assert result["variant"] == "backend-node"
    assert result["content"].startswith("# Tailored Resume")
    assert repo.get_tailored_resume(jid)["content"] == result["content"]


def test_tailor_requires_a_score(tmp_db):
    jid = tmp_db.insert_job_if_new(
        dedup_hash="d2", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="u", posted_date=None,
    )
    assert "error" in services.tailor_for_job(jid)  # unscored → no variant


def test_draft_cover_persists_and_lists(tmp_db, monkeypatch):
    jid = _scored_job(tmp_db)
    monkeypatch.setattr(cover, "chat", lambda *a, **k: "Dear Acme team, I build NestJS APIs...")

    result = services.draft_cover_for_job(jid)
    assert result["kind"] == DraftKind.COVER
    assert "NestJS" in result["body"]

    drafts = services.list_drafts(jid)
    assert len(drafts) == 1 and drafts[0]["kind"] == "cover"
