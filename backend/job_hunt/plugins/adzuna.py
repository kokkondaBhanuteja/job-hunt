"""Adzuna job source plugin — official job-search API, free registration.

Adzuna is a free official job aggregator API. No authentication hassle,
full job descriptions in results. One API call per page, paginated results.
Discovered jobs are stored with full JD and transition straight to ENRICHED.

`_fetch` is module-level so tests can monkeypatch it (no network).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)


def _fetch(
    country: str, what: str, where: str, page: int, app_id: str, app_key: str,
) -> dict[str, Any]:
    """Fetch one page of results from Adzuna job API."""
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": what,
        "where": where,
        "results_per_page": 20,
    }
    resp = httpx.get(url, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


class AdzunaSource:
    name = "adzuna"

    def discover(
        self, *, keyword: str, location: str = "in", pages: int = 1,
        headless: bool = True, dry_run: bool = False,
    ) -> dict[str, Any]:
        """Discover jobs from Adzuna API."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []

        app_id = os.getenv("ADZUNA_APP_ID")
        app_key = os.getenv("ADZUNA_APP_KEY")
        country = os.getenv("ADZUNA_COUNTRY", "in")

        if not app_id or not app_key:
            logger.warning(
                "Adzuna: missing ADZUNA_APP_ID or ADZUNA_APP_KEY; skipping discovery"
            )
            return {"found": 0, "new": 0, "jobs": []}

        for page in range(1, pages + 1):
            try:
                data = _fetch(country, keyword, location, page, app_id, app_key)
            except httpx.HTTPError as e:
                logger.warning(f"Adzuna page {page} fetch failed: {e}; continuing")
                continue

            for r in data.get("results", []):
                title = r.get("title")
                if not title:
                    continue
                company = (r.get("company") or {}).get("display_name") or "Unknown"
                loc = (r.get("location") or {}).get("display_name") or location
                desc = r.get("description") or ""
                apply_url = r.get("redirect_url")
                sid = str(r.get("id") or "")
                created = r.get("created")

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": loc,
                    "apply_url": apply_url,
                })
                found += 1

                if dry_run:
                    continue

                if persist_full_jd_job(
                    source="adzuna",
                    source_job_id=sid,
                    title=title,
                    company=company,
                    location=loc,
                    full_jd=strip_html(desc),
                    apply_url=apply_url,
                    posted_date=created,
                    raw_payload={},
                ):
                    new += 1

        return {"found": found, "new": new, "jobs": jobs}


register(AdzunaSource())
