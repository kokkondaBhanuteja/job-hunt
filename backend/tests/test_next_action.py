"""Tests for the rule-based next_best_action recommender.

Advisory-only: every test verifies the correct action is recommended without
any writes or state changes to the job record.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from job_hunt import services
from job_hunt.enums import EmailActionState, EmailCategory, JobState

# ---------- helpers ----------


def _insert_job(db, *, state: str, h: str = "na1") -> int:
    """Insert a minimal job row and forcibly set its state."""
    jid = db.insert_job_if_new(
        dedup_hash=h,
        source="naukri",
        source_job_id=None,
        title="Test Job",
        company="Corp",
        location="remote",
        description="desc",
        apply_url="https://example.com",
        posted_date=None,
    )
    with db.connect() as conn:
        conn.execute("UPDATE jobs SET state = ? WHERE id = ?", (state, jid))
    return jid


def _insert_variant(db, slug: str = "v1") -> int:
    return db.upsert_resume_variant(
        slug=slug, source_path="/x", parsed={"h": 1}, tags=[]
    )


def _insert_application(
    db,
    job_id: int,
    variant_id: int,
    *,
    days_ago: int = 1,
    reply_type: str | None = None,
) -> None:
    """Insert an applications row with a controllable applied_at timestamp."""
    applied_at = (datetime.now(UTC) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO applications "
            "(job_id, variant_id, cover_letter, applied_at, reply_type, stage) "
            "VALUES (?, ?, ?, ?, ?, 'applied')",
            (job_id, variant_id, "cover", applied_at, reply_type),
        )


def _insert_email(
    db,
    job_id: int,
    *,
    category: str = EmailCategory.RECRUITER_OUTREACH,
    action_state: str = EmailActionState.NONE,
    uid: int = 1,
) -> None:
    """Insert a minimal email_messages row linked to a job."""
    with db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO email_messages "
            "(mailbox, uid, job_id, category, action_state, created_at) "
            "VALUES ('INBOX', ?, ?, ?, ?, '2024-01-01T00:00:00')",
            (uid, job_id, category, action_state),
        )


# ---------- parametrised state-based rules ----------


@pytest.mark.parametrize(
    "state, expected_action",
    [
        (JobState.OFFER, "negotiate"),
        (JobState.INTERVIEW, "prep"),
        (JobState.HR, "prep"),
        (JobState.ENRICHED, "score"),
        (JobState.DISCOVERED, "score"),
        (JobState.REJECTED, "none"),
        (JobState.WITHDRAWN, "none"),
        (JobState.ARCHIVED, "none"),
        (JobState.DEFERRED, "review"),
    ],
)
def test_state_rules(tmp_db, state, expected_action):
    """State-based rules produce the expected action without any application row."""
    jid = _insert_job(tmp_db, state=state, h=f"nr-{state}")
    result = services.next_best_action(jid)
    assert result["action"] == expected_action, f"state={state}: {result}"
    assert "reason" in result


# ---------- missing job ----------


def test_missing_job_returns_error(tmp_db):
    """next_best_action returns {error: ...} for a non-existent job."""
    result = services.next_best_action(99999)
    assert "error" in result
    assert "99999" in result["error"]


# ---------- SCORED rules ----------


def test_scored_strong_fit_recommends_apply(tmp_db):
    """SCORED job with fit_score >= 75 → action='apply'."""
    jid = _insert_job(tmp_db, state=JobState.SCORED, h="ns-strong")
    vid = _insert_variant(tmp_db, slug="v-s1")
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=80, reasoning="good")
    result = services.next_best_action(jid)
    assert result["action"] == "apply"
    assert "80" in result["reason"]


def test_scored_low_fit_recommends_review(tmp_db):
    """SCORED job with fit_score < 75 → action='review'."""
    jid = _insert_job(tmp_db, state=JobState.SCORED, h="ns-low")
    vid = _insert_variant(tmp_db, slug="v-s2")
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=60, reasoning="weak")
    result = services.next_best_action(jid)
    assert result["action"] == "review"
    assert "60" in result["reason"]


def test_scored_exact_threshold_recommends_apply(tmp_db):
    """SCORED job with fit_score == 75 (boundary) → action='apply'."""
    jid = _insert_job(tmp_db, state=JobState.SCORED, h="ns-boundary")
    vid = _insert_variant(tmp_db, slug="v-s3")
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=75, reasoning="ok")
    result = services.next_best_action(jid)
    assert result["action"] == "apply"


# ---------- APPLIED follow-up rules ----------


def test_old_applied_no_reply_recommends_follow_up(tmp_db):
    """APPLIED with applied_at >= 7 days ago and no reply_type → action='follow_up'."""
    jid = _insert_job(tmp_db, state=JobState.APPLIED, h="ns-old")
    vid = _insert_variant(tmp_db, slug="v-a1")
    _insert_application(tmp_db, jid, vid, days_ago=8, reply_type=None)
    result = services.next_best_action(jid)
    assert result["action"] == "follow_up"
    assert "days ago" in result["reason"]


def test_recent_applied_recommends_wait(tmp_db):
    """APPLIED with applied_at < 7 days ago → action='wait'."""
    jid = _insert_job(tmp_db, state=JobState.APPLIED, h="ns-recent")
    vid = _insert_variant(tmp_db, slug="v-a2")
    _insert_application(tmp_db, jid, vid, days_ago=2, reply_type=None)
    result = services.next_best_action(jid)
    assert result["action"] == "wait"


def test_old_applied_with_reply_recommends_wait(tmp_db):
    """APPLIED >= 7 days ago but reply_type is set → action='wait' (not follow_up)."""
    jid = _insert_job(tmp_db, state=JobState.APPLIED, h="ns-replied")
    vid = _insert_variant(tmp_db, slug="v-a3")
    _insert_application(tmp_db, jid, vid, days_ago=10, reply_type="interview")
    result = services.next_best_action(jid)
    assert result["action"] == "wait"


def test_oa_old_no_reply_recommends_follow_up(tmp_db):
    """OA state (>= 7 days, no reply) also triggers follow_up."""
    jid = _insert_job(tmp_db, state=JobState.OA, h="ns-oa")
    vid = _insert_variant(tmp_db, slug="v-a4")
    _insert_application(tmp_db, jid, vid, days_ago=9, reply_type=None)
    result = services.next_best_action(jid)
    assert result["action"] == "follow_up"


# ---------- email precedence ----------


def test_linked_recruiter_email_takes_priority_over_state(tmp_db):
    """An unreplied recruiter email overrides state-based rules (fires first)."""
    jid = _insert_job(tmp_db, state=JobState.OFFER, h="ns-email-prio")
    _insert_email(
        tmp_db, jid, category=EmailCategory.RECRUITER_OUTREACH,
        action_state=EmailActionState.NONE,
    )
    result = services.next_best_action(jid)
    # Even though state=OFFER would normally → negotiate, the email fires first.
    assert result["action"] == "reply"


def test_acted_email_does_not_trigger_reply(tmp_db):
    """An email with action_state != none does not trigger the reply rule."""
    jid = _insert_job(tmp_db, state=JobState.OFFER, h="ns-email-done")
    _insert_email(
        tmp_db, jid, category=EmailCategory.RECRUITER_OUTREACH,
        action_state=EmailActionState.EXECUTED, uid=2,
    )
    result = services.next_best_action(jid)
    # Email is actioned → falls through to state rule → negotiate.
    assert result["action"] == "negotiate"


def test_rejection_email_does_not_trigger_reply(tmp_db):
    """A rejection or confirmation email (non-recruiter category) does not trigger reply."""
    jid = _insert_job(tmp_db, state=JobState.SCORED, h="ns-rej-email")
    vid = _insert_variant(tmp_db, slug="v-re1")
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=80, reasoning="ok")
    _insert_email(
        tmp_db, jid, category=EmailCategory.REJECTION,
        action_state=EmailActionState.NONE, uid=3,
    )
    # Rejection email is not a recruiter email → no reply rule → falls to SCORED apply.
    result = services.next_best_action(jid)
    assert result["action"] == "apply"


# ---------- no writes / advisory only ----------


def test_next_best_action_does_not_mutate_job_state(tmp_db):
    """next_best_action must not change the job's state column."""
    jid = _insert_job(tmp_db, state=JobState.SCORED, h="ns-nomut")
    vid = _insert_variant(tmp_db, slug="v-nm1")
    tmp_db.write_score(job_id=jid, variant_id=vid, fit_score=80, reasoning="ok")

    with tmp_db.connect() as conn:
        before = conn.execute("SELECT state FROM jobs WHERE id = ?", (jid,)).fetchone()["state"]

    services.next_best_action(jid)

    with tmp_db.connect() as conn:
        after = conn.execute("SELECT state FROM jobs WHERE id = ?", (jid,)).fetchone()["state"]

    assert before == after
