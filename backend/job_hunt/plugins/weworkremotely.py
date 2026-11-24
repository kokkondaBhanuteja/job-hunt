"""We Work Remotely source plugin — public RSS feed, no auth."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

logger = get_logger(__name__)

WWR_RSS = "https://weworkremotely.com/remote-jobs.rss"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch(url: str = WWR_RSS) -> str:
    """Fetch the We Work Remotely RSS feed and return the raw XML text."""
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


def _split_company_title(raw_title: str) -> tuple[str, str]:
    """Split 'Company: Role' into (company, title), falling back gracefully."""
    if ": " in raw_title:
        company, _, title = raw_title.partition(": ")
        return company.strip(), title.strip()
    return "Unknown", raw_title.strip()


class WeWorkRemotelySource:
    name = "weworkremotely"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "remote",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Fetch We Work Remotely RSS, filter by keyword, persist new jobs."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []

        try:
            xml_text = _fetch()
        except Exception:
            logger.exception("WeWorkRemotely _fetch failed")
            return {"found": 0, "new": 0, "jobs": []}

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.exception("WeWorkRemotely: failed to parse RSS XML")
            return {"found": 0, "new": 0, "jobs": []}

        for item in root.findall(".//item"):
            try:
                raw_title = (item.findtext("title") or "").strip()
                company, title = _split_company_title(raw_title)
                link = (item.findtext("link") or "").strip()
                description = strip_html(item.findtext("description") or "")
                pub_date = (item.findtext("pubDate") or "").strip() or None
                guid = (item.findtext("guid") or link).strip()
                # Every WWR job is remote; <region> says where ("USA Only", "Anywhere in
                # the World"). Store it so the India/remote location filter can see it.
                region = (item.findtext("region") or "").strip()
                job_location = f"Remote - {region}" if region else location

                if not _matches(keyword, title, description):
                    continue

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
                    source="weworkremotely",
                    source_job_id=guid,
                    title=title,
                    company=company,
                    location=job_location,
                    full_jd=description,
                    apply_url=link,
                    posted_date=pub_date,
                ):
                    new += 1
            except Exception:
                logger.exception("WeWorkRemotely: error parsing item, skipping")

        return {"found": found, "new": new, "jobs": jobs}


register(WeWorkRemotelySource())
