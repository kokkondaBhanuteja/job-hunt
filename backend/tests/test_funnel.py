"""Tests for funnel_metrics() — interview/offer rates, time-to-interview, and source rates."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from job_hunt import services
from job_hunt.enums import ReplyType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job(db, *, source: str = "remoteok", suffix: str = "1") -> int:
    """Insert a job and return its id (returns None on dup — callers pass unique suffixes)."""
    jid = db.insert_job_if_new(
        dedup_hash=f"funnelhash{suffix}",
        source=source,
        source_job_id=None,
        title="Engineer",
        company="Acme",
        location="remote",
        description="d",
        apply_url="u",
        posted_date=None,
    )
    assert jid is not None, f"job {suffix} was unexpectedly a duplicate"
    return jid


def _apply(db, job_id: int, *, stage: str = "applied", reply_type: str | None = None) -> None:
    """Record an application at the given stage and optionally set reply_type."""
    db.upsert_resume_variant(slug="v", source_path="/x", parsed={"h": 1}, tags=[])
    services.log_application(job_id, "v", "cover", status="applied")
    if stage != "applied":
        services.advance_stage(job_id, stage)
    if reply_type is not None:
        with db.connect() as conn:
            conn.execute(
                "UPDATE applications SET reply_type = ? WHERE job_id = ?",
                (reply_type, job_id),
            )


def _insert_transition(db, job_id: int, to_state: str, *, ts: str) -> None:
    """Directly insert a job_transition row with the given ISO timestamp."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO job_transitions (job_id, from_state, to_state, reason, created_at) "
            "VALUES (?, NULL, ?, NULL, ?)",
            (job_id, to_state, ts),
        )


# ---------------------------------------------------------------------------
# interview_rate / offer_rate
# ---------------------------------------------------------------------------


def test_interview_and_offer_rates(tmp_db):
    j1 = _job(tmp_db, suffix="ir1")
    j2 = _job(tmp_db, suffix="ir2")
    j3 = _job(tmp_db, suffix="ir3")

    _apply(tmp_db, j1, stage="interview")   # counts as interview
    _apply(tmp_db, j2, stage="offer")       # counts as interview AND offer
    _apply(tmp_db, j3, stage="applied")     # no stage progress

    m = services.funnel_metrics()

    assert m["applications_total"] == 3
    assert m["interviews"] == 2       # interview + offer both qualify
    assert m["offers"] == 1
    assert m["interview_rate"] == round(2 / 3, 3)
    assert m["offer_rate"] == round(1 / 3, 3)


def test_rejections_count(tmp_db):
    j1 = _job(tmp_db, suffix="rj1")
    j2 = _job(tmp_db, suffix="rj2")
    _apply(tmp_db, j1, stage="rejected")
    _apply(tmp_db, j2, stage="applied")

    m = services.funnel_metrics()
    assert m["rejections"] == 1


# ---------------------------------------------------------------------------
# divide-by-zero guard
# ---------------------------------------------------------------------------


def test_divide_by_zero_returns_zero_point_zero(tmp_db):
    m = services.funnel_metrics()
    assert m["applications_total"] == 0
    assert m["interview_rate"] == 0.0
    assert m["offer_rate"] == 0.0
    assert m["response_rate"] == 0.0
    assert m["stage_conversion"]["applied_to_interview"] == 0.0
    assert m["stage_conversion"]["interview_to_offer"] == 0.0


# ---------------------------------------------------------------------------
# stage_conversion
# ---------------------------------------------------------------------------


def test_stage_conversion_interview_to_offer(tmp_db):
    j1 = _job(tmp_db, suffix="sc1")
    j2 = _job(tmp_db, suffix="sc2")
    j3 = _job(tmp_db, suffix="sc3")

    _apply(tmp_db, j1, stage="interview")
    _apply(tmp_db, j2, stage="interview")
    _apply(tmp_db, j3, stage="offer")

    m = services.funnel_metrics()
    # interviews = 3 (2 interview + 1 offer), offers = 1
    assert m["stage_conversion"]["interview_to_offer"] == round(1 / 3, 3)


# ---------------------------------------------------------------------------
# time_to_interview_days (median)
# ---------------------------------------------------------------------------


def test_time_to_interview_median_even_count(tmp_db):
    """Median of [3, 7] = (3 + 7) / 2 = 5.0."""
    now = datetime.now(UTC)

    j1 = _job(tmp_db, suffix="tti1")
    j2 = _job(tmp_db, suffix="tti2")

    def ts(days_ago: float) -> str:
        return (now - timedelta(days=days_ago)).isoformat()

    # j1: applied 10 days ago, interview 7 days ago → delta = 3 days
    _insert_transition(tmp_db, j1, "applied", ts=ts(10))
    _insert_transition(tmp_db, j1, "interview", ts=ts(7))

    # j2: applied 10 days ago, interview 3 days ago → delta = 7 days
    _insert_transition(tmp_db, j2, "applied", ts=ts(10))
    _insert_transition(tmp_db, j2, "interview", ts=ts(3))

    m = services.funnel_metrics()
    assert m["time_to_interview_days"] == 5.0


def test_time_to_interview_median_odd_count(tmp_db):
    """Median of [3, 5, 7] = 5.0."""
    now = datetime.now(UTC)

    j1 = _job(tmp_db, suffix="ttio1")
    j2 = _job(tmp_db, suffix="ttio2")
    j3 = _job(tmp_db, suffix="ttio3")

    def ts(days_ago: float) -> str:
        return (now - timedelta(days=days_ago)).isoformat()

    _insert_transition(tmp_db, j1, "applied", ts=ts(13))
    _insert_transition(tmp_db, j1, "interview", ts=ts(10))   # delta 3

    _insert_transition(tmp_db, j2, "applied", ts=ts(10))
    _insert_transition(tmp_db, j2, "interview", ts=ts(5))    # delta 5

    _insert_transition(tmp_db, j3, "applied", ts=ts(7))
    _insert_transition(tmp_db, j3, "interview", ts=ts(0))    # delta 7

    m = services.funnel_metrics()
    assert m["time_to_interview_days"] == 5.0


def test_time_to_interview_none_when_no_transitions(tmp_db):
    m = services.funnel_metrics()
    assert m["time_to_interview_days"] is None


def test_time_to_interview_none_when_only_applied_transitions(tmp_db):
    """A job with only an applied transition (no interview) yields None."""
    now = datetime.now(UTC)
    j1 = _job(tmp_db, suffix="ttionly")
    _insert_transition(tmp_db, j1, "applied", ts=now.isoformat())

    m = services.funnel_metrics()
    assert m["time_to_interview_days"] is None


# ---------------------------------------------------------------------------
# source_effectiveness_by_outcome
# ---------------------------------------------------------------------------


def test_source_effectiveness_by_outcome(tmp_db):
    j1 = _job(tmp_db, source="remoteok", suffix="se1")
    j2 = _job(tmp_db, source="remoteok", suffix="se2")
    j3 = _job(tmp_db, source="linkedin", suffix="se3")

    _apply(tmp_db, j1, stage="interview")
    _apply(tmp_db, j2, stage="applied")
    _apply(tmp_db, j3, stage="offer")   # offer counts as interview

    m = services.funnel_metrics()
    by_source = {r["source"]: r for r in m["source_effectiveness_by_outcome"]}

    ro = by_source["remoteok"]
    assert ro["applied"] == 2
    assert ro["interviews"] == 1
    assert ro["offers"] == 0
    assert ro["interview_rate"] == 0.5

    li = by_source["linkedin"]
    assert li["applied"] == 1
    assert li["interviews"] == 1   # offer stage counts as interview
    assert li["offers"] == 1
    assert li["interview_rate"] == 1.0


# ---------------------------------------------------------------------------
# response_rate
# ---------------------------------------------------------------------------


def test_response_rate(tmp_db):
    j1 = _job(tmp_db, suffix="rr1")
    j2 = _job(tmp_db, suffix="rr2")
    j3 = _job(tmp_db, suffix="rr3")

    _apply(tmp_db, j1, reply_type=ReplyType.INTERVIEW)
    _apply(tmp_db, j2, reply_type=ReplyType.REJECT)
    _apply(tmp_db, j3)   # no reply

    m = services.funnel_metrics()
    assert m["response_rate"] == round(2 / 3, 3)


# ---------------------------------------------------------------------------
# integration: funnel_metrics present in dashboard()
# ---------------------------------------------------------------------------


def test_funnel_metrics_key_in_dashboard(tmp_db):
    d = services.dashboard()
    assert "funnel_metrics" in d
    fm = d["funnel_metrics"]
    assert "applications_total" in fm
    assert "interview_rate" in fm
    assert "stage_conversion" in fm
    assert "source_effectiveness_by_outcome" in fm
    # legacy funnel key must still be present
    assert "funnel" in d
