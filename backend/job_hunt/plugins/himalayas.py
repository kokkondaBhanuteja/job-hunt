"""Himalayas source plugin — public JSON search API, no browser, no auth.

The search endpoint can return only jobs a given country may apply for
(``country=IN``: India-restricted roles plus roles open worldwide), which is what
makes this board useful from India. ``locationRestrictions`` becomes the stored
location ("Remote - India", "Remote - Egypt, India, Pakistan", or "Remote - Worldwide"
when empty), so the shared India/remote location filter still applies.
"""
from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

HIMALAYAS_SEARCH_API = "https://himalayas.app/jobs/api/search"
HIMALAYAS_COUNTRY = os.getenv("HIMALAYAS_COUNTRY", "IN").strip()
HIMALAYAS_MAX_PAGES = int(os.getenv("HIMALAYAS_MAX_PAGES", "3"))  # 20 jobs per page
HIMALAYAS_PAGE_DELAY_S = float(os.getenv("HIMALAYAS_PAGE_DELAY_S", "1.0"))
_UA = "job-hunt/1.0"


def _fetch(params: dict[str, Any]) -> dict[str, Any]:
    """Call the Himalayas search API and return the parsed JSON payload."""
    resp = httpx.get(HIMALAYAS_SEARCH_API, params=params, headers={"User-Agent": _UA},
                     timeout=30.0)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


def _location(row: dict[str, Any]) -> str:
    """Return "Remote - <allowed countries>", or "Remote - Worldwide" when unrestricted."""
    allowed = [c for c in (row.get("locationRestrictions") or []) if c]
    return f"Remote - {', '.join(allowed)}" if allowed else "Remote - Worldwide"


def _posted(value: Any) -> str | None:
    """Return an ISO date for a Unix-seconds pubDate, passing strings through."""
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC).date().isoformat()
    return str(value) if value else None


class HimalayasSource:
    name = "himalayas"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "remote",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Search Himalayas for India-eligible jobs matching keyword; persist new ones."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []
        max_pages = max(1, HIMALAYAS_MAX_PAGES)

        for page in range(1, max_pages + 1):
            params: dict[str, Any] = {"q": keyword, "page": page}
            if HIMALAYAS_COUNTRY:
                params["country"] = HIMALAYAS_COUNTRY
            try:
                payload = _fetch(params)
            except Exception:
                logger.exception("Himalayas _fetch failed (page %d)", page)
                break

            rows: list[dict[str, Any]] = payload.get("jobs") or []
            for row in rows:
                try:
                    title = row.get("title") or ""
                    if not title:
                        continue
                    company = row.get("companyName") or "Unknown"
                    loc = _location(row)
                    apply_url = row.get("applicationLink") or ""
                    description = strip_html(row.get("description") or row.get("excerpt") or "")

                    jobs.append({"title": title, "company": company, "location": loc,
                                 "apply_url": apply_url})
                    found += 1
                    if dry_run:
                        continue
                    if persist_full_jd_job(
                        source="himalayas",
                        source_job_id=str(row.get("guid") or apply_url),
                        title=title,
                        company=company,
                        location=loc,
                        full_jd=description,
                        apply_url=apply_url,
                        posted_date=_posted(row.get("pubDate")),
                        raw_payload={"seniority": row.get("seniority") or [],
                                     "timezones": row.get("timezoneRestrictions") or []},
                    ):
                        new += 1
                except Exception:
                    logger.exception("Himalayas: error parsing job row, skipping")

            total = int(payload.get("totalCount") or 0)
            if not rows or page * len(rows) >= total:
                break
            time.sleep(HIMALAYAS_PAGE_DELAY_S)

        return {"found": found, "new": new, "jobs": jobs}


register(HimalayasSource())
