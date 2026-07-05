"""Workable source — public widget API, one company at a time.

`keyword` is the company account slug, e.g. keyword="stripe" pulls
https://apply.workable.com/api/v1/widget/accounts/stripe?details=true.
`_fetch` is module-level for test monkeypatching.
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

API = "https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"


def _fetch(token: str) -> list[dict[str, Any]]:
    """Fetch job listings from the Workable public widget API for the given token."""
    resp = httpx.get(API.format(token=token), timeout=30.0)
    resp.raise_for_status()
    return resp.json().get("jobs", [])


class WorkableSource:
    name = "workable"

    def discover(
        self, *, keyword: str, location: str = "", pages: int = 1,
        headless: bool = True, dry_run: bool = False,
    ) -> dict[str, Any]:
        """Crawl the Workable board for a given company slug and persist new jobs."""
        token = keyword.strip().lower()
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []
        try:
            raw_jobs = _fetch(token)
        except Exception:  # noqa: BLE001
            logger.warning("workable: board fetch failed for token %r", token, exc_info=True)
            return {"found": 0, "new": 0, "jobs": []}
        for row in raw_jobs:
            try:
                title = row.get("title")
                if not title:
                    continue
                loc_data = row.get("location") or {}
                loc = (
                    loc_data
                    if isinstance(loc_data, str)
                    else f"{loc_data.get('city', '')}, {loc_data.get('country', '')}".strip(", ")
                )
                if location and location.lower() not in loc.lower():
                    continue
                found += 1
                apply_url = row.get("url") or row.get("shortlink")
                jobs.append({"title": title, "company": token, "location": loc,
                             "apply_url": apply_url})
                if dry_run:
                    continue
                full_jd = strip_html(row.get("description") or "")
                source_job_id = str(row.get("id") or row.get("shortcode") or "")
                if persist_full_jd_job(
                    source="workable",
                    source_job_id=source_job_id,
                    title=title,
                    company=token,
                    location=loc,
                    full_jd=full_jd,
                    apply_url=apply_url,
                    posted_date=row.get("published_on"),
                ):
                    new += 1
            except Exception:  # noqa: BLE001 — log and continue; don't break the crawl
                logger.warning("workable: failed to process job row, skipping", exc_info=True)
        return {"found": found, "new": new, "jobs": jobs}


register(WorkableSource())
