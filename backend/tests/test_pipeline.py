"""The event-driven pipeline auto-advances: discovered → enriched → scored.

Uses stub fetcher + stub scorer (no browser / no LLM); drives the worker's real
handler registry through the real event bus.
"""
from __future__ import annotations

from job_hunt.enums import JobState
from job_hunt.events import bus
from job_hunt.states import mark_discovered
from job_hunt.storage import repo
from job_hunt.worker.handlers import build_handlers


def test_pipeline_discovered_enriched_scored(tmp_db):
    jid = tmp_db.insert_job_if_new(
        dedup_hash="p1", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="snippet", apply_url="https://x/1", posted_date=None,
    )
    mark_discovered(jid)  # emits JOB_DISCOVERED

    scored = {"calls": 0}
    handlers = build_handlers(
        enrich_fetchers={"naukri": lambda url: "The full job description text."},
        score_job_fn=lambda job_id: scored.__setitem__("calls", scored["calls"] + 1),
    )

    # Round 1: JOB_DISCOVERED → enrich → job becomes ENRICHED (emits JOB_ENRICHED).
    assert bus.dispatch_pending(handlers) == 1
    assert repo.get_job_state(jid) == JobState.ENRICHED
    assert repo.get_job(jid)["description_full"] == "The full job description text."

    # Round 2: JOB_ENRICHED → scorer runs.
    assert bus.dispatch_pending(handlers) == 1
    assert scored["calls"] == 1

    # Round 3: nothing left.
    assert bus.dispatch_pending(handlers) == 0
