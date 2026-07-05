"""Remotive source plugin — public JSON API, no browser, no auth.

Remotive asks for ≤4 API calls/day and requires attribution. Therefore this plugin is
NOT in the worker's fast loop — use it for manual/CLI invocations only.
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

REMOTIVE_API = "https://remotive.com/api/remote-jobs"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch(url: str) -> dict[str, Any]:
    """Fetch the Remotive API and return the parsed JSON payload."""
    resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _matches(keyword: str, title: str, tags: list[str]) -> bool:
    """Return True if any keyword token appears in title or tags."""
    tokens = [t for t in keyword.lower().split() if t]
    if not tokens:
        return True
    hay = f"{title} {' '.join(tags)}".lower()
    return any(t in hay for t in tokens)


class RemotiveSource:
    name = "remotive"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "remote",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Fetch Remotive jobs, filter by keyword, persist new ones."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []

        url = REMOTIVE_API
        if keyword:
            url = f"{REMOTIVE_API}?search={keyword}"

        try:
            payload = _fetch(url)
        except Exception:
            logger.exception("Remotive _fetch failed")
            return {"found": 0, "new": 0, "jobs": []}

        for row in payload.get("jobs") or []:
            try:
                title = row.get("title") or ""
                tags: list[str] = row.get("tags") or []
                if not _matches(keyword, title, tags):
                    continue

                company = row.get("company_name") or "Unknown"
                loc = row.get("candidate_required_location") or location
                apply_url = row.get("url")
                description = strip_html(row.get("description") or "")
                source_job_id = str(row.get("id") or "")
                posted_date = row.get("publication_date")

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": loc,
                    "apply_url": apply_url,
                    "tags": tags,
                })
                found += 1

                if dry_run:
                    continue

                if persist_full_jd_job(
                    source="remotive",
                    source_job_id=source_job_id,
                    title=title,
                    company=company,
                    location=loc,
                    full_jd=description,
                    apply_url=apply_url,
                    posted_date=posted_date,
                    raw_payload={"tags": tags},
                ):
                    new += 1
            except Exception:
                logger.exception("Remotive: error parsing job row, skipping")

        return {"found": found, "new": new, "jobs": jobs}


register(RemotiveSource())
