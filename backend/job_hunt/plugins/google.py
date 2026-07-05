"""Google Careers source plugin — public JSON search API, no auth required.

Searches Google's public job listings via the careers.google.com v3 API.
Discovered jobs are stored with full JD and transition straight to ENRICHED.
`_fetch` is module-level so tests can monkeypatch it (no network).

Note: the v3 endpoint requires a browser session in some network environments;
HTTP errors are caught and logged so the worker loop is never interrupted.
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

_GOOGLE_API = "https://careers.google.com/api/v3/search/"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch(keyword: str, location: str, page_size: int = 20) -> dict[str, Any]:
    """Fetch job search results from the Google Careers v3 API."""
    params: dict[str, Any] = {
        "q": keyword,
        "page_size": page_size,
        "sort_by": "relevance",
        "hl": "en_US",
    }
    if location and location.lower() != "remote":
        params["location"] = location
    resp = httpx.get(_GOOGLE_API, params=params, headers={"User-Agent": _UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


class GoogleSource:
    name = "google"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "remote",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Discover jobs from Google Careers API and persist them."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []

        try:
            data = _fetch(keyword, location, page_size=20 * pages)
        except httpx.HTTPError as exc:
            logger.warning("Google: fetch failed: %s", exc)
            return {"found": 0, "new": 0, "jobs": []}

        for item in data.get("jobs", []):
            try:
                title = item.get("title")
                if not title:
                    continue

                company = item.get("company_name") or "Google"

                # locations is a list of objects; use the first display value
                locs = item.get("locations") or []
                loc = (locs[0].get("display") if locs and isinstance(locs[0], dict) else None) or location

                apply_url = item.get("apply_url")
                sid = str(item.get("id") or item.get("job_id") or "")
                published = item.get("publish_date")
                description = item.get("description") or item.get("summary") or ""

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
                    source="google",
                    source_job_id=sid,
                    title=title,
                    company=company,
                    location=loc,
                    full_jd=strip_html(description),
                    apply_url=apply_url,
                    posted_date=published,
                    raw_payload={},
                ):
                    new += 1

            except Exception as exc:  # noqa: BLE001 — skip bad items, keep the crawl alive
                logger.warning("Google: skipping item due to parse error: %s", exc)

        return {"found": found, "new": new, "jobs": jobs}


register(GoogleSource())
