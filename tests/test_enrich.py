"""Tests for the enrichment engine (fetcher injected — no browser)."""
from __future__ import annotations

from job_hunt.enrich import service as enrich
from job_hunt.enums import EventType, JobState
from job_hunt.storage import repo


def _job(db, h="e1"):
    return db.insert_job_if_new(
        dedup_hash=h, source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="snippet", apply_url="https://x/1", posted_date=None,
    )


def test_enrich_job_stores_full_jd_transitions_and_emits(tmp_db):
    jid = _job(tmp_db)
    ok = enrich.enrich_job(jid, lambda url: "A full job description with real requirements.")
    assert ok is True

    assert repo.get_job_state(jid) == JobState.ENRICHED
    job = repo.get_job(jid)
    assert job["description_full"].startswith("A full job description")
    assert str(EventType.JOB_ENRICHED) in [e["type"] for e in repo.fetch_unprocessed_events()]


def test_enrich_job_is_noop_when_already_enriched(tmp_db):
    jid = _job(tmp_db)
    assert enrich.enrich_job(jid, lambda url: "first") is True
    # Second call sees description_full already set → no-op.
    assert enrich.enrich_job(jid, lambda url: "second") is False


def test_enrich_job_skips_empty_fetch(tmp_db):
    jid = _job(tmp_db)
    assert enrich.enrich_job(jid, lambda url: None) is False
    assert repo.get_job_state(jid) == JobState.DISCOVERED


def test_enrich_pending_drives_by_source(tmp_db):
    _job(tmp_db, h="e-a")
    _job(tmp_db, h="e-b")
    result = enrich.enrich_pending({"naukri": lambda url: "full jd text here"}, limit=10)
    assert result == {"candidates": 2, "enriched": 2}
