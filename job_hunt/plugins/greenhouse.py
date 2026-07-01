"""Greenhouse source — public board API, one company at a time.

`keyword` is the board token (the company's Greenhouse slug), e.g. discover
keyword="stripe" pulls https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true.
Greenhouse returns the full JD in `content`, so jobs land already-ENRICHED.
`_fetch` is module-level for test monkeypatching.
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


def _fetch(board: str) -> list[dict[str, Any]]:
    resp = httpx.get(API.format(board=board), timeout=30.0)
    resp.raise_for_status()
    return resp.json().get("jobs", [])


class GreenhouseSource:
    name = "greenhouse"

    def discover(
        self, *, keyword: str, location: str = "", pages: int = 1,
        headless: bool = True, dry_run: bool = False,
    ) -> dict[str, Any]:
        board = keyword.strip().lower()
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []
        for row in _fetch(board):
            title = row.get("title")
            if not title:
                continue
            loc = (row.get("location") or {}).get("name") or ""
            if location and location.lower() not in loc.lower():
                continue
            found += 1
            jobs.append({"title": title, "company": board, "location": loc,
                         "apply_url": row.get("absolute_url")})
            if dry_run:
                continue
            if persist_full_jd_job(
                source="greenhouse", source_job_id=str(row.get("id") or ""),
                title=title, company=board, location=loc,
                full_jd=strip_html(row.get("content", "")),
                apply_url=row.get("absolute_url"), posted_date=row.get("updated_at"),
            ):
                new += 1
        return {"found": found, "new": new, "jobs": jobs}


register(GreenhouseSource())
