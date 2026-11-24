"""Instahyre source plugin — the site's own JSON job search, no login.

Instahyre lists India jobs only (44k at the time of writing; Bangalore, Hyderabad,
Mumbai, Pune...). Its search endpoint is the one the website itself calls; it is
allowed by robots.txt but is not a documented public API, so this plugin stays small
and polite: ``INSTAHYRE_MAX_PAGES`` pages per keyword, ``INSTAHYRE_PAGE_DELAY_S``
between requests, and it stops at the first error. The keyword maps to the ``skills``
filter (the site ignores location/experience parameters). Jobs carry no full
description, so title, skills and the company note are stored as the JD for scoring.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx

from job_hunt.logging_config import get_logger
from job_hunt.plugins._persist import persist_full_jd_job
from job_hunt.plugins.base import register

logger = get_logger(__name__)

INSTAHYRE_API = "https://www.instahyre.com/api/v1/job_search"
INSTAHYRE_MAX_PAGES = int(os.getenv("INSTAHYRE_MAX_PAGES", "3"))
INSTAHYRE_PAGE_DELAY_S = float(os.getenv("INSTAHYRE_PAGE_DELAY_S", "1.5"))
_PAGE_SIZE = 35  # the site's own page size
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_INDIA = re.compile(r"\bindia\b", re.IGNORECASE)


def _fetch(params: dict[str, Any]) -> dict[str, Any]:
    """Call the Instahyre job search and return the parsed JSON payload."""
    resp = httpx.get(INSTAHYRE_API, params=params, headers={"User-Agent": _UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


def _skills_query(keyword: str) -> str:
    """Return the skills filter for a profile keyword ("backend engineer" -> "backend")."""
    tokens = [t for t in re.split(r"[\s,]+", keyword.strip()) if t]
    generic = {"engineer", "developer", "sde", "senior", "junior", "lead", "software"}
    specific = [t for t in tokens if t.lower() not in generic]
    return (specific or tokens or [""])[0]


def _location(raw: str | None) -> str:
    """Return the job's locations, marked as India (every Instahyre job is in India)."""
    locations = (raw or "").strip()
    if not locations:
        return "India"
    return locations if _INDIA.search(locations) else f"{locations}, India"


def _description(row: dict[str, Any], company: str) -> str:
    employer = row.get("employer") if isinstance(row.get("employer"), dict) else {}
    parts = [
        f"{row.get('title') or ''} at {company}",
        f"Locations: {row.get('locations') or 'India'}",
        f"Skills: {', '.join(str(k) for k in row.get('keywords') or [])}",
        str(employer.get("company_tagline") or ""),
        str(employer.get("instahyre_note") or ""),
    ]
    return "\n".join(p for p in parts if p.strip())


class InstahyreSource:
    name = "instahyre"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Search Instahyre by skill for India jobs; persist new ones."""
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []
        skills = _skills_query(keyword)

        for page in range(max(1, INSTAHYRE_MAX_PAGES)):
            params: dict[str, Any] = {"limit": _PAGE_SIZE, "offset": page * _PAGE_SIZE}
            if skills:
                params["skills"] = skills
            try:
                payload = _fetch(params)
            except Exception:
                logger.exception("Instahyre _fetch failed (offset %d); stopping", page * _PAGE_SIZE)
                break

            rows: list[dict[str, Any]] = payload.get("objects") or []
            for row in rows:
                try:
                    title = (row.get("title") or row.get("candidate_title") or "").strip()
                    if not title:
                        continue
                    employer = row.get("employer") if isinstance(row.get("employer"), dict) else {}
                    company = str(employer.get("company_name") or "Unknown")
                    loc = _location(row.get("locations"))
                    apply_url = row.get("public_url") or ""

                    jobs.append({"title": title, "company": company, "location": loc,
                                 "apply_url": apply_url})
                    found += 1
                    if dry_run:
                        continue
                    if persist_full_jd_job(
                        source="instahyre",
                        source_job_id=str(row.get("id") or apply_url),
                        title=title,
                        company=company,
                        location=loc,
                        full_jd=_description(row, company),
                        apply_url=apply_url,
                        posted_date=row.get("reviewed_at"),
                        raw_payload={"keywords": row.get("keywords") or []},
                    ):
                        new += 1
                except Exception:
                    logger.exception("Instahyre: error parsing job row, skipping")

            meta = payload.get("meta") or {}
            if not rows or not meta.get("next"):
                break
            time.sleep(INSTAHYRE_PAGE_DELAY_S)

        return {"found": found, "new": new, "jobs": jobs}


register(InstahyreSource())
