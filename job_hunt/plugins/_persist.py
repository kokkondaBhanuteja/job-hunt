"""Shared helpers for API sources that ship the full JD at discovery.

Such jobs skip the browser enrich step: they're stored already-enriched and transition
straight to ENRICHED, entering the scoring pipeline. Cross-source dedup via the canonical key.
"""
from __future__ import annotations

import re
from typing import Any

from job_hunt.enums import JobState
from job_hunt.sources.dedup import dedup_hash
from job_hunt.states import mark_discovered, transition_job
from job_hunt.storage.repo import insert_job_if_new, set_job_enriched

_TAG = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return _TAG.sub(" ", text or "").replace("&amp;", "&").strip()


def persist_full_jd_job(
    *, source: str, source_job_id: str | None, title: str, company: str,
    location: str, full_jd: str, apply_url: str | None,
    posted_date: str | None = None, raw_payload: dict[str, Any] | None = None,
) -> bool:
    """Insert a job (with full JD → ENRICHED). Returns True if new, False if a duplicate."""
    job_id = insert_job_if_new(
        dedup_hash=dedup_hash(company, title, location or ""),
        source=source, source_job_id=source_job_id, title=title, company=company,
        location=location, description=(full_jd[:400] or None),
        apply_url=apply_url or "", posted_date=posted_date, raw_payload=raw_payload,
    )
    if job_id is None:
        return False
    if full_jd:
        set_job_enriched(job_id, full_jd)
        try:
            transition_job(job_id, JobState.ENRICHED, reason="api-full-jd")
        except Exception:  # noqa: BLE001
            pass
    else:
        mark_discovered(job_id)
    return True
