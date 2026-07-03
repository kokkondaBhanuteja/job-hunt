"""Lever source — public postings API, one company at a time.

`keyword` is the company token, e.g. keyword="netflix" pulls
https://api.lever.co/v0/postings/netflix?mode=json. Lever returns `descriptionPlain`
(full JD), so jobs land already-ENRICHED. `_fetch` is module-level for test monkeypatching.
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.plugins._persist import persist_full_jd_job
from job_hunt.plugins.base import register

API = "https://api.lever.co/v0/postings/{company}?mode=json"


def _fetch(company: str) -> list[dict[str, Any]]:
    resp = httpx.get(API.format(company=company), timeout=30.0)
    resp.raise_for_status()
    return resp.json()


class LeverSource:
    name = "lever"

    def discover(
        self, *, keyword: str, location: str = "", pages: int = 1,
        headless: bool = True, dry_run: bool = False,
    ) -> dict[str, Any]:
        company = keyword.strip().lower()
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []
        for row in _fetch(company):
            title = row.get("text")
            if not title:
                continue
            loc = (row.get("categories") or {}).get("location") or ""
            if location and location.lower() not in loc.lower():
                continue
            found += 1
            jobs.append({"title": title, "company": company, "location": loc,
                         "apply_url": row.get("hostedUrl")})
            if dry_run:
                continue
            if persist_full_jd_job(
                source="lever", source_job_id=str(row.get("id") or ""),
                title=title, company=company, location=loc,
                full_jd=(row.get("descriptionPlain") or "").strip(),
                apply_url=row.get("hostedUrl"), posted_date=str(row.get("createdAt") or ""),
            ):
                new += 1
        return {"found": found, "new": new, "jobs": jobs}


register(LeverSource())
