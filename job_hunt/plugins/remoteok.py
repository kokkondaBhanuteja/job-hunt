"""RemoteOK source plugin — public JSON API, no browser, no auth.

Demonstrates the plugin system: one file + `register()` and the whole pipeline (dedup,
scoring, board) works. RemoteOK ships the **full JD** in its API, so discovered jobs are
stored already-enriched and transition straight to ENRICHED → the event pipeline scores
them. Cross-source dedup (canonical key) collapses the same role found on Naukri too.

`_fetch` is module-level so tests can monkeypatch it (no network).
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from job_hunt.enums import JobState
from job_hunt.plugins.base import register
from job_hunt.sources.dedup import dedup_hash
from job_hunt.states import mark_discovered, transition_job
from job_hunt.storage.repo import insert_job_if_new, set_job_enriched

REMOTEOK_API = "https://remoteok.com/api"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG.sub(" ", text or "").replace("&amp;", "&").strip()


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
            full_jd = _strip_html(row.get("description", ""))
            jobs.append({"title": position, "company": company, "location": loc,
                         "apply_url": row.get("url"), "tags": tags})
            found += 1
            if dry_run:
                continue

            job_id = insert_job_if_new(
                dedup_hash=dedup_hash(company, position, loc),
                source="remoteok", source_job_id=str(row.get("id") or ""),
                title=position, company=company, location=loc,
                description=(full_jd[:400] or None), apply_url=row.get("url") or "",
                posted_date=row.get("date"), raw_payload={"tags": tags},
            )
            if job_id is None:  # cross-source duplicate
                continue
            new += 1
            if full_jd:  # RemoteOK gives the full JD up front → skip enrichment
                set_job_enriched(job_id, full_jd)
                try:
                    transition_job(job_id, JobState.ENRICHED, reason="api-full-jd")
                except Exception:  # noqa: BLE001
                    pass
            else:
                mark_discovered(job_id)

        return {"found": found, "new": new, "jobs": jobs}


register(RemoteOKSource())
