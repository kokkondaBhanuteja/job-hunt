"""Enrichment services — wire each source's optional `enrich` capability to the engine."""
from __future__ import annotations

from typing import Any

from job_hunt.enrich.service import enrich_pending
from job_hunt.plugins import available_sources, get_source


def source_enrich_fetchers(*, headless: bool = True) -> dict[str, Any]:
    """{source_name: fetch(url)} for every registered source that implements `enrich`."""
    fetchers: dict[str, Any] = {}
    for name in available_sources():
        enrich = getattr(get_source(name), "enrich", None)
        if enrich is not None:
            fetchers[name] = lambda url, fn=enrich: fn(url, headless=headless)
    return fetchers


def enrich_pending_jobs(*, limit: int = 50, headless: bool = True) -> dict[str, Any]:
    """Fetch full JDs for DISCOVERED jobs, using each source's own enrich capability."""
    return enrich_pending(source_enrich_fetchers(headless=headless), limit=limit)
