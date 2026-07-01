"""Enrichment services — wire the per-source JD fetchers to the enrich engine."""
from __future__ import annotations

from typing import Any

from job_hunt.enrich.service import enrich_pending
from job_hunt.sources.naukri import fetch_job_description_sync


def enrich_pending_jobs(*, limit: int = 50, headless: bool = True) -> dict[str, Any]:
    """Fetch full JDs for DISCOVERED jobs (Naukri for now)."""
    fetchers = {"naukri": lambda url: fetch_job_description_sync(url, headless=headless)}
    return enrich_pending(fetchers, limit=limit)
