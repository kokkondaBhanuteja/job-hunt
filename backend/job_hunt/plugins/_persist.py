"""Shared helpers for API sources that ship the full JD at discovery.

Such jobs skip the browser enrich step: they're stored already-enriched and transition
straight to ENRICHED, entering the scoring pipeline. Cross-source dedup via the canonical key.
"""
from __future__ import annotations

import re
from typing import Any

from job_hunt.enums import JobState
from job_hunt.logging_config import get_logger
from job_hunt.sources.dedup import dedup_hash
from job_hunt.sources.location import is_india_or_open_remote
from job_hunt.states import transition_job
from job_hunt.storage.repo import insert_job_if_new, set_job_enriched

logger = get_logger(__name__)
_TAG = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return _TAG.sub(" ", text or "").replace("&amp;", "&").strip()


def persist_full_jd_job(
    *, source: str, source_job_id: str | None, title: str, company: str,
    location: str, full_jd: str, apply_url: str | None,
    posted_date: str | None = None, raw_payload: dict[str, Any] | None = None,
) -> bool:
    """Insert a job (with full JD → ENRICHED). Return True if new; False if a duplicate or
    outside the location filter (India or remote open to India; see sources/location.py)."""
    if not is_india_or_open_remote(location, title):
        logger.debug("skip %s job outside location filter: %r", source, location)
        return False
    job_id = insert_job_if_new(
        dedup_hash=dedup_hash(company, title, location or ""),
        source=source, source_job_id=source_job_id, title=title, company=company,
        location=location, description=(full_jd[:400] or None),
        apply_url=apply_url or "", posted_date=posted_date, raw_payload=raw_payload,
        emit_discovered=True,  # row + JOB_DISCOVERED atomically (no orphans)
    )
    if job_id is None:
        return False
    if full_jd:  # API sources ship the full JD → advance straight to ENRICHED
        set_job_enriched(job_id, full_jd)
        try:
            transition_job(job_id, JobState.ENRICHED, reason="api-full-jd")
        except Exception:  # noqa: BLE001 — don't break the crawl, but don't hide it either
            logger.warning("job %s enriched but ENRICHED transition failed (won't be scored)",
                           job_id, exc_info=True)
    return True
