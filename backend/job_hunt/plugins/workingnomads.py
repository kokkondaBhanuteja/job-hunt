"""Working Nomads source plugin — public JSON API, no auth.

The old RSS address (/jobsrss) now returns 404; the site serves the same jobs as JSON
at /api/exposed_jobs/, including a real per-job location ("Global", "CET (+/- 3 hours)",
"Europe, LATAM, APAC, the U.S., Canada"). Every job is remote, so it is stored as
"Remote - <location>" for the shared India/remote location filter.
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

WORKINGNOMADS_API = "https://www.workingnomads.com/api/exposed_jobs/"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch(url: str = WORKINGNOMADS_API) -> list[dict[str, Any]]:
    """Fetch the Working Nomads JSON API and return the list of job rows."""
    resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _matches(keyword: str, title: str, description: str) -> bool:
    """Return True if any keyword token appears in title or description."""
    tokens = [t for t in keyword.lower().split() if t]
    if not tokens:
        return True
    hay = f"{title} {description}".lower()
    return any(t in hay for t in tokens)


class WorkingNomadsSource:
    name = "workingnomads"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "remote",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Fetch Working Nomads jobs, filter by keyword, persist new jobs."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []

        try:
            rows = _fetch()
        except Exception:
            logger.exception("WorkingNomads _fetch failed")
            return {"found": 0, "new": 0, "jobs": []}

        for row in rows:
            try:
                title = (row.get("title") or "").strip()
                if not title:
                    continue
                link = (row.get("url") or "").strip()
                description = strip_html(row.get("description") or "")
                if not _matches(keyword, title, description):
                    continue
                company = (row.get("company_name") or "Unknown").strip()
                region = (row.get("location") or "").strip()
                job_location = f"Remote - {region}" if region else location

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "apply_url": link,
                })
                found += 1

                if dry_run:
                    continue

                if persist_full_jd_job(
                    source="workingnomads",
                    source_job_id=link,
                    title=title,
                    company=company,
                    location=job_location,
                    full_jd=description,
                    apply_url=link,
                    posted_date=row.get("pub_date"),
                    raw_payload={"category": row.get("category_name"),
                                 "tags": row.get("tags")},
                ):
                    new += 1
            except Exception:
                logger.exception("WorkingNomads: error parsing job row, skipping")

        return {"found": found, "new": new, "jobs": jobs}


register(WorkingNomadsSource())
