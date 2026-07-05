"""Amazon Jobs source plugin — public JSON search API, no auth required.

Searches Amazon's public job listings via the search.json endpoint.
Discovered jobs are stored with full JD and transition straight to ENRICHED.
`_fetch` is module-level so tests can monkeypatch it (no network).
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

_AMAZON_API = "https://www.amazon.jobs/en/search.json"
_BASE_URL = "https://www.amazon.jobs"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch(keyword: str, location: str, result_limit: int = 20) -> dict[str, Any]:
    """Fetch job search results from the Amazon Jobs search.json API."""
    params: dict[str, Any] = {
        "base_query": keyword,
        "loc_query": location,
        "result_limit": result_limit,
        "sort": "recent",
    }
    resp = httpx.get(_AMAZON_API, params=params, headers={"User-Agent": _UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


class AmazonSource:
    name = "amazon"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "remote",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Discover jobs from Amazon Jobs API and persist them."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []

        try:
            data = _fetch(keyword, location, result_limit=20 * pages)
        except httpx.HTTPError as exc:
            logger.warning("Amazon: fetch failed: %s", exc)
            return {"found": 0, "new": 0, "jobs": []}

        for item in data.get("jobs", []):
            try:
                title = item.get("title")
                if not title:
                    continue

                company = item.get("company_name") or "Amazon"
                loc = item.get("normalized_location") or item.get("location") or location
                job_path = item.get("job_path") or ""
                apply_url = f"{_BASE_URL}{job_path}" if job_path else None
                sid = str(item.get("id_icims") or job_path or "")
                posted = item.get("posted_date")
                description = item.get("description") or item.get("description_short") or ""

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
                    source="amazon",
                    source_job_id=sid,
                    title=title,
                    company=company,
                    location=loc,
                    full_jd=strip_html(description),
                    apply_url=apply_url,
                    posted_date=posted,
                    raw_payload={},
                ):
                    new += 1

            except Exception as exc:  # noqa: BLE001 — skip bad items, keep the crawl alive
                logger.warning("Amazon: skipping item due to parse error: %s", exc)

        return {"found": found, "new": new, "jobs": jobs}


register(AmazonSource())
