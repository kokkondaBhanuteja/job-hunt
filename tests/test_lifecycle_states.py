"""B1: the drafting/apply services now drive the pursuit funnel — SCORED → TAILORING_READY
→ DRAFTED → REVIEW_PENDING — and emit the (previously dead) RESUME_TAILORED/DRAFT_GENERATED
events. Out-of-order calls degrade gracefully (advance_if_legal)."""
from __future__ import annotations

from job_hunt import services
from job_hunt.apply import reviewer
from job_hunt.enums import JobState
from job_hunt.services import drafting
from job_hunt.states import transition_job
from job_hunt.storage import repo


def _scored_job(tmp_db):
    jid = tmp_db.insert_job_if_new(
        dedup_hash="lc1", source="naukri", source_job_id=None, title="Backend Engineer",
        company="Acme", location="blr", description="NestJS", apply_url="u", posted_date=None,
    )
    vid = tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=88, reasoning="ok")
    transition_job(jid, JobState.SCORED)  # discovered → scored (legal)
    return jid


def test_pursuit_funnel_advances_and_emits_events(tmp_db, monkeypatch):
    jid = _scored_job(tmp_db)
    monkeypatch.setattr(drafting, "tailor_resume", lambda **k: "# tailored")
    monkeypatch.setattr(drafting, "generate_cover_letter", lambda **k: "Dear team,")
    monkeypatch.setattr(reviewer, "chat_json", lambda *a, **k: {"ready": True, "issues": []})

    services.tailor_for_job(jid)
    assert repo.get_job_state(jid) == JobState.TAILORING_READY

    services.draft_cover_for_job(jid)
    assert repo.get_job_state(jid) == JobState.DRAFTED

    services.prepare_application(jid, [])
    assert repo.get_job_state(jid) == JobState.REVIEW_PENDING

    with tmp_db.connect() as conn:
        types = {r["type"] for r in conn.execute("SELECT DISTINCT type FROM events").fetchall()}
    assert "resume.tailored" in types and "draft.generated" in types  # were never emitted before


def test_out_of_order_call_is_graceful(tmp_db, monkeypatch):
    # A cover-letter call on a job still in DISCOVERED must not raise or wrongly jump state.
    jid = tmp_db.insert_job_if_new(
        dedup_hash="lc2", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="u", posted_date=None,
    )
    tmp_db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    tmp_db.write_score(job_id=jid, variant_id=1, fit_score=70, reasoning="ok")
    monkeypatch.setattr(drafting, "generate_cover_letter", lambda **k: "hi")

    services.draft_cover_for_job(jid)  # job is 'discovered' → DRAFTED not legal → no-op
    assert repo.get_job_state(jid) == JobState.DISCOVERED
