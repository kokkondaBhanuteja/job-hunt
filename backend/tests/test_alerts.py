"""Tests for instant per-match alerts: on_scored handler + passes_policy predicate.

Verifies alert-only behavior (no state change, no auto-apply) and dedup via
LearningKind.ALERT. Uses a stub notifier — no Telegram calls are made.
"""
from __future__ import annotations

from typing import Any

from job_hunt.enums import LearningKind
from job_hunt.services import apply_policy as ap
from job_hunt.storage import repo
from job_hunt.worker import handlers

# ---------- stub notifier ----------


class _FakeNotifier:
    name = "fake"
    calls: list[str]

    def __init__(self) -> None:
        self.calls = []

    def send(self, text: str) -> bool:
        """Capture the message; always succeeds."""
        self.calls.append(text)
        return True


# ---------- seed helpers ----------


def _seed_job(
    db,
    *,
    title: str = "Python Backend Engineer",
    company: str = "Acme Corp",
    description: str = "python django aws",
    apply_url: str = "https://example.com/apply",
    h: str | None = None,
) -> int:
    """Insert a job and return its id."""
    job_id = db.insert_job_if_new(
        dedup_hash=h or title.lower().replace(" ", "-"),
        source="naukri",
        source_job_id=None,
        title=title,
        company=company,
        location="remote",
        description=description,
        apply_url=apply_url,
        posted_date=None,
    )
    assert job_id is not None
    return job_id


def _seed_variant(db) -> int:
    return db.upsert_resume_variant(
        slug="backend-py",
        source_path="/x.tex",
        parsed={"headline": "Backend", "skills": {"languages": ["python"]}},
        tags=["python"],
    )


def _score(db, job_id: int, variant_id: int, score: int) -> None:
    db.write_score(job_id=job_id, variant_id=variant_id, fit_score=score, reasoning="stub")


def _make_event(job_id: int) -> dict[str, Any]:
    return {"id": 1, "payload": {"job_id": job_id}}


# ---------- passes_policy unit tests ----------


def test_passes_policy_must_have_present():
    """Job text contains the must_have keyword → passes."""
    job = {"title": "Python Backend", "company": "Acme", "location": "remote",
           "description": "python django", "description_full": ""}
    policy = {"must_have": ["python"], "avoid": [], "remote_only": False, "seniority": ""}
    assert ap.passes_policy(job, policy) is True


def test_passes_policy_must_have_absent():
    """Job text missing the must_have keyword → fails."""
    job = {"title": "Go Backend", "company": "Acme", "location": "remote",
           "description": "golang kubernetes", "description_full": ""}
    policy = {"must_have": ["python"], "avoid": [], "remote_only": False, "seniority": ""}
    assert ap.passes_policy(job, policy) is False


def test_passes_policy_avoid_present():
    """Job text contains an avoid keyword → fails."""
    job = {"title": "Python Crypto Engineer", "company": "Acme", "location": "remote",
           "description": "blockchain defi", "description_full": ""}
    policy = {"must_have": [], "avoid": ["crypto"], "remote_only": False, "seniority": ""}
    assert ap.passes_policy(job, policy) is False


def test_passes_policy_avoid_absent():
    """Job text does not contain avoid keyword → passes."""
    job = {"title": "Python Backend Engineer", "company": "Acme", "location": "remote",
           "description": "python django", "description_full": ""}
    policy = {"must_have": [], "avoid": ["crypto"], "remote_only": False, "seniority": ""}
    assert ap.passes_policy(job, policy) is True


def test_passes_policy_empty_policy_always_passes():
    """Default/empty policy → every job passes."""
    job = {"title": "Anything", "company": "Corp", "location": "onsite",
           "description": "java spring", "description_full": ""}
    policy = {"must_have": [], "avoid": [], "remote_only": False, "seniority": ""}
    assert ap.passes_policy(job, policy) is True


# ---------- on_scored handler tests ----------


def test_on_scored_sends_alert_above_policy_bar(tmp_db, monkeypatch):
    """Score above bar + policy passes → exactly one alert sent, ALERT learning recorded."""
    notifier = _FakeNotifier()
    monkeypatch.setattr(handlers, "get_notifier", lambda: notifier)

    vid = _seed_variant(tmp_db)
    jid = _seed_job(tmp_db, h="alert-1")
    _score(tmp_db, jid, vid, 85)

    repo.set_apply_policy(
        {"min_fit_score": 70, "must_have": ["python"], "avoid": [], "seniority": "", "remote_only": False}
    )

    handlers.on_scored(_make_event(jid))

    assert len(notifier.calls) == 1
    assert "Python Backend Engineer" in notifier.calls[0]
    assert "85" in notifier.calls[0]

    learnings = repo.list_learnings_for_job(jid)
    assert any(row["kind"] == str(LearningKind.ALERT) for row in learnings)


def test_on_scored_dedup_no_second_alert(tmp_db, monkeypatch):
    """Second on_scored call for the same job → no second notification (dedup)."""
    notifier = _FakeNotifier()
    monkeypatch.setattr(handlers, "get_notifier", lambda: notifier)

    vid = _seed_variant(tmp_db)
    jid = _seed_job(tmp_db, h="alert-2")
    _score(tmp_db, jid, vid, 85)

    repo.set_apply_policy(
        {"min_fit_score": 70, "must_have": [], "avoid": [], "seniority": "", "remote_only": False}
    )

    handlers.on_scored(_make_event(jid))
    handlers.on_scored(_make_event(jid))  # second call — must be a no-op

    assert len(notifier.calls) == 1


def test_on_scored_below_score_bar_no_alert(tmp_db, monkeypatch):
    """fit_score below min_fit_score → no alert sent."""
    notifier = _FakeNotifier()
    monkeypatch.setattr(handlers, "get_notifier", lambda: notifier)

    vid = _seed_variant(tmp_db)
    jid = _seed_job(tmp_db, h="alert-3")
    _score(tmp_db, jid, vid, 50)

    repo.set_apply_policy(
        {"min_fit_score": 70, "must_have": [], "avoid": [], "seniority": "", "remote_only": False}
    )

    handlers.on_scored(_make_event(jid))

    assert notifier.calls == []


def test_on_scored_fails_must_have_no_alert(tmp_db, monkeypatch):
    """Job score is above bar but must_have keyword absent → no alert."""
    notifier = _FakeNotifier()
    monkeypatch.setattr(handlers, "get_notifier", lambda: notifier)

    vid = _seed_variant(tmp_db)
    jid = _seed_job(tmp_db, title="Go Backend Engineer", description="golang kubernetes", h="alert-4")
    _score(tmp_db, jid, vid, 85)

    repo.set_apply_policy(
        {"min_fit_score": 70, "must_have": ["python"], "avoid": [], "seniority": "", "remote_only": False}
    )

    handlers.on_scored(_make_event(jid))

    assert notifier.calls == []


def test_on_scored_hits_avoid_keyword_no_alert(tmp_db, monkeypatch):
    """Job contains an avoid keyword → no alert even if score is above bar."""
    notifier = _FakeNotifier()
    monkeypatch.setattr(handlers, "get_notifier", lambda: notifier)

    vid = _seed_variant(tmp_db)
    jid = _seed_job(tmp_db, title="Python Crypto Engineer", description="blockchain defi", h="alert-5")
    _score(tmp_db, jid, vid, 90)

    repo.set_apply_policy(
        {"min_fit_score": 70, "must_have": [], "avoid": ["crypto"], "seniority": "", "remote_only": False}
    )

    handlers.on_scored(_make_event(jid))

    assert notifier.calls == []


def test_on_scored_missing_job_is_silent(tmp_db, monkeypatch):
    """on_scored with a non-existent job_id → no crash, no alert."""
    notifier = _FakeNotifier()
    monkeypatch.setattr(handlers, "get_notifier", lambda: notifier)

    handlers.on_scored(_make_event(99999))

    assert notifier.calls == []


def test_on_scored_no_state_change(tmp_db, monkeypatch):
    """on_scored must not alter the job's state."""
    notifier = _FakeNotifier()
    monkeypatch.setattr(handlers, "get_notifier", lambda: notifier)

    vid = _seed_variant(tmp_db)
    jid = _seed_job(tmp_db, h="alert-6")
    _score(tmp_db, jid, vid, 85)

    state_before = repo.get_job_state(jid)
    handlers.on_scored(_make_event(jid))
    state_after = repo.get_job_state(jid)

    assert state_before == state_after


def test_default_handlers_includes_job_scored(monkeypatch):
    """default_handlers registers on_scored under EventType.JOB_SCORED."""
    from job_hunt.enums import EventType
    from job_hunt.services import enrichment

    monkeypatch.setattr(enrichment, "source_enrich_fetchers", lambda **_: {})
    h = handlers.default_handlers()
    assert str(EventType.JOB_SCORED) in h
    assert h[str(EventType.JOB_SCORED)] is handlers.on_scored
