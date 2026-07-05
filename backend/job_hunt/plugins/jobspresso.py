"""Jobspresso source plugin — WP Job Manager RSS feed, no auth."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

JOBSPRESSO_RSS = "https://jobspresso.co/feed/?post_type=job_listing"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch(url: str = JOBSPRESSO_RSS) -> str:
    """Fetch the Jobspresso RSS feed and return the raw XML text."""
    resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def _matches(keyword: str, title: str, description: str) -> bool:
    """Return True if any keyword token appears in title or description."""
    tokens = [t for t in keyword.lower().split() if t]
    if not tokens:
        return True
    hay = f"{title} {description}".lower()
    return any(t in hay for t in tokens)


def _extract_company(item: ET.Element, title: str) -> str:
    """Extract company from WP Job Manager namespace element or title, best-effort."""
    # WP Job Manager may emit <job_listing:company> or similar namespaced elements
    for child in item:
        local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if local in ("company", "company_name") and child.text:
            return child.text.strip()
    # Fall back: "Company: Role" pattern in title
    if ": " in title:
        return title.split(": ", 1)[0].strip()
    return "Unknown"


class JobspressoSource:
    name = "jobspresso"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "remote",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Fetch Jobspresso RSS, filter by keyword, persist new jobs."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []

        try:
            xml_text = _fetch()
        except Exception:
            logger.exception("Jobspresso _fetch failed")
            return {"found": 0, "new": 0, "jobs": []}

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.exception("Jobspresso: failed to parse RSS XML")
            return {"found": 0, "new": 0, "jobs": []}

        for item in root.findall(".//item"):
            try:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                description = strip_html(item.findtext("description") or "")
                pub_date = (item.findtext("pubDate") or "").strip() or None
                guid = (item.findtext("guid") or link).strip()
                company = _extract_company(item, title)

                if not _matches(keyword, title, description):
                    continue

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "apply_url": link,
                })
                found += 1

                if dry_run:
                    continue

                if persist_full_jd_job(
                    source="jobspresso",
                    source_job_id=guid,
                    title=title,
                    company=company,
                    location=location,
                    full_jd=description,
                    apply_url=link,
                    posted_date=pub_date,
                ):
                    new += 1
            except Exception:
                logger.exception("Jobspresso: error parsing item, skipping")

        return {"found": found, "new": new, "jobs": jobs}


register(JobspressoSource())
