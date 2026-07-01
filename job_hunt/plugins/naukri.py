"""Naukri source plugin — adapts the existing crawler to the Source contract."""
from __future__ import annotations

from typing import Any

from job_hunt.plugins.base import register
from job_hunt.sources.naukri import crawl_sync


class NaukriSource:
    name = "naukri"

    def discover(
        self, *, keyword: str, location: str, pages: int = 1,
        headless: bool = True, dry_run: bool = False,
    ) -> dict[str, Any]:
        return crawl_sync(keyword, location, pages=pages, headless=headless, dry_run=dry_run)


register(NaukriSource())
