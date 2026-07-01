"""RemoteOK source plugin — public JSON API, no browser, no auth.

Demonstrates the plugin system: one file + `register()` and the whole pipeline (dedup,
scoring, board) works. RemoteOK ships the **full JD** in its API, so discovered jobs are
stored already-enriched and transition straight to ENRICHED → the event pipeline scores
them. Cross-source dedup (canonical key) collapses the same role found on Naukri too.

`_fetch` is module-level so tests can monkeypatch it (no network).
"""
from __future__ import annotations

from typing import Any

import httpx

from job_hunt.plugins._persist import persist_full_jd_job, strip_html
from job_hunt.plugins.base import register

REMOTEOK_API = "https://remoteok.com/api"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _fetch(url: str = REMOTEOK_API) -> list[dict[str, Any]]:
    resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _matches(keyword: str, position: str, tags: list[str]) -> bool:
    tokens = [t for t in keyword.lower().split() if t]
    if not tokens:
        return True
    hay = f"{position} {' '.join(tags)}".lower()
    return any(t in hay for t in tokens)


class RemoteOKSource:
    name = "remoteok"

    def discover(
        self, *, keyword: str, location: str = "remote", pages: int = 1,
        headless: bool = True, dry_run: bool = False,
    ) -> dict[str, Any]:
        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []

        for row in _fetch():
            position = row.get("position")
            if not position:  # first element is legal/metadata
                continue
            tags = row.get("tags") or []
            if not _matches(keyword, position, tags):
                continue

            company = row.get("company") or "Unknown"
            loc = row.get("location") or "Remote"
            jobs.append({"title": position, "company": company, "location": loc,
                         "apply_url": row.get("url"), "tags": tags})
            found += 1
            if dry_run:
                continue
            if persist_full_jd_job(
                source="remoteok", source_job_id=str(row.get("id") or ""),
                title=position, company=company, location=loc,
                full_jd=strip_html(row.get("description", "")),
                apply_url=row.get("url"), posted_date=row.get("date"),
                raw_payload={"tags": tags},
            ):
                new += 1

        return {"found": found, "new": new, "jobs": jobs}


register(RemoteOKSource())
