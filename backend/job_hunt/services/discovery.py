"""Discovery services — crawl a source and persist new jobs."""
from __future__ import annotations

from typing import Any

from job_hunt import plugins
from job_hunt.sources.naukri import crawl_sync as _naukri_crawl
from job_hunt.storage.repo import init_db


def discover(
    source: str,
    keyword: str,
    location: str,
    pages: int = 1,
    *,
    dry_run: bool = False,
    headless: bool = True,
) -> dict[str, Any]:
    """Discover jobs from any registered source. Returns {found, new, jobs}."""
    init_db()
    return plugins.get_source(source).discover(
        keyword=keyword, location=location, pages=pages, dry_run=dry_run, headless=headless
    )


def discover_naukri(
    keyword: str,
    location: str,
    pages: int = 1,
    *,
    dry_run: bool = False,
    headless: bool = True,
) -> dict[str, Any]:
    """Crawl Naukri for (keyword, location); persist new jobs. Returns {found, new, jobs}."""
    init_db()
    return _naukri_crawl(keyword, location, pages=pages, dry_run=dry_run, headless=headless)
