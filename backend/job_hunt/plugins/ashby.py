"""Ashby source — public board API, one company at a time.

`keyword` is the board token e.g. discover keyword="stripe" pulls
https://api.ashbyhq.com/posting-api/job-board/stripe?includeCompensation=true.
`_fetch` is module-level for test monkeypatching.
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

API = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"


def _fetch(token: str) -> list[dict[str, Any]]:
    """Fetch job listings from the Ashby public board API for the given token."""
    resp = httpx.get(API.format(token=token), timeout=30.0)
    resp.raise_for_status()
    return resp.json().get("jobs", [])


class AshbySource:
    name = "ashby"

    def discover(
        self, *, keyword: str, location: str = "", pages: int = 1,
        headless: bool = True, dry_run: bool = False,
    ) -> dict[str, Any]:
        """Crawl the Ashby board for a given company token and persist new jobs."""
        token = keyword.strip().lower()
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []
        try:
            raw_jobs = _fetch(token)
        except Exception:  # noqa: BLE001
            logger.warning("ashby: board fetch failed for token %r", token, exc_info=True)
            return {"found": 0, "new": 0, "jobs": []}
        for row in raw_jobs:
            try:
                title = row.get("title")
                if not title:
                    continue
                loc_data = row.get("location") or ""
                loc = loc_data if isinstance(loc_data, str) else (
                    loc_data.get("name") or loc_data.get("city") or ""
                )
                if location and location.lower() not in loc.lower():
                    continue
                found += 1
                apply_url = row.get("jobUrl") or row.get("applyUrl")
                jobs.append({"title": title, "company": token, "location": loc,
                             "apply_url": apply_url})
                if dry_run:
                    continue
                full_jd = row.get("descriptionPlain") or strip_html(row.get("descriptionHtml") or "")
                if persist_full_jd_job(
                    source="ashby",
                    source_job_id=str(row.get("id") or ""),
                    title=title,
                    company=token,
                    location=loc,
                    full_jd=full_jd,
                    apply_url=apply_url,
                    posted_date=row.get("publishedAt"),
                ):
                    new += 1
            except Exception:  # noqa: BLE001 — log and continue; don't break the crawl
                logger.warning("ashby: failed to process job row, skipping", exc_info=True)
        return {"found": found, "new": new, "jobs": jobs}


register(AshbySource())
