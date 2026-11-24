"""Workday source — public no-auth careers-page API.

`keyword` is the careers-site spec: ``{tenant}.{dc}.myworkdayjobs.com/{site}``
(e.g. ``qualcomm.wd5.myworkdayjobs.com/External``). An optional leading
``https://`` is stripped. The plugin POSTs to Workday's public CXS endpoint,
applies a module-level politeness throttle (default 4 h per token), and persists
discovered jobs via ``persist_full_jd_job``. No login, no credentials, no HTML
scraping — public JSON endpoint only.

Filtering: big boards hold thousands of postings worldwide, so the newest page
rarely contains the roles you want. With ``WORKDAY_COUNTRY`` set (default India)
the plugin reads the board's own facets, selects that country (each tenant names
its facets differently), searches ``WORKDAY_SEARCH_TEXT`` and pages through up to
``WORKDAY_MAX_PAGES`` pages. An empty ``WORKDAY_COUNTRY`` restores the unfiltered
newest-postings behaviour.
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

WORKDAY_MIN_INTERVAL_S: int = int(os.getenv("WORKDAY_MIN_INTERVAL_S", "14400"))
WORKDAY_COUNTRY: str = os.getenv("WORKDAY_COUNTRY", "India").strip()
WORKDAY_SEARCH_TEXT: str = os.getenv("WORKDAY_SEARCH_TEXT", "software engineer").strip()
WORKDAY_MAX_PAGES: int = int(os.getenv("WORKDAY_MAX_PAGES", "5"))
WORKDAY_PAGE_DELAY_S: float = float(os.getenv("WORKDAY_PAGE_DELAY_S", "1.0"))
_PAGE_SIZE = 20  # Workday's CXS endpoint rejects larger pages

_WORKDAY_HOST_RE = re.compile(
    r'^(?:https?://)?'
    r'(?P<host>(?P<tenant>[a-z0-9-]+)\.[a-z0-9]+\.myworkdayjobs\.com)'
    r'/(?P<site>[^/?#].*)$',
    re.IGNORECASE,
)

# Throttle state: token → last successful fetch timestamp (monotonic)
_last_fetch: dict[str, float] = {}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _fetch(
    host: str,
    tenant: str,
    site: str,
    search_text: str,
    *,
    applied_facets: dict[str, list[str]] | None = None,
    offset: int = 0,
    limit: int = _PAGE_SIZE,
) -> dict[str, Any]:
    """POST the Workday CXS jobs endpoint and return the parsed JSON response."""
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    payload: dict[str, Any] = {
        "appliedFacets": applied_facets or {},
        "limit": limit,
        "offset": offset,
        "searchText": search_text,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


def country_facets(facets: list[dict[str, Any]], country: str) -> dict[str, list[str]]:
    """Return ``appliedFacets`` that select *country* on this board, or {} if it has none.

    Prefers a single exact country value (e.g. a "Country" facet's "India"); otherwise
    selects every location under the country ("India - Bangalore", "Bengaluru, India"),
    matching on word boundaries so "India" never selects "Indiana".
    """
    wanted = country.strip().lower()
    leading = re.compile(rf"^{re.escape(country)}\b", re.IGNORECASE)
    trailing = re.compile(rf",\s*{re.escape(country)}\s*$", re.IGNORECASE)
    exact: list[tuple[str, str, str]] = []  # (facetParameter, label, value id)
    locations: dict[str, list[str]] = {}

    for facet in facets:
        param = facet.get("facetParameter") or ""
        label = f"{param} {facet.get('descriptor') or ''}".lower()
        for value in facet.get("values") or []:
            if "values" in value:  # grouped facet, e.g. locationMainGroup → locations
                sub_param = value.get("facetParameter") or ""
                ids = [v["id"] for v in value["values"]
                       if leading.match(v.get("descriptor") or "")
                       or trailing.search(v.get("descriptor") or "")]
                if sub_param and ids:
                    locations.setdefault(sub_param, []).extend(ids)
                continue
            descriptor = (value.get("descriptor") or "").strip()
            if descriptor.lower() == wanted and param:
                exact.append((param, label, value["id"]))
            elif "location" in label and param and (
                leading.match(descriptor) or trailing.search(descriptor)
            ):
                locations.setdefault(param, []).append(value["id"])

    if exact:
        param, _label, value_id = next((e for e in exact if "country" in e[1]), exact[0])
        return {param: [value_id]}
    return locations


class WorkdaySource:
    name = "workday"

    def discover(
        self,
        *,
        keyword: str,
        location: str = "",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Crawl a Workday careers site and persist new jobs. Return {found, new, jobs}."""
        empty: dict[str, Any] = {"found": 0, "new": 0, "jobs": []}

        m = _WORKDAY_HOST_RE.match(keyword.strip())
        if not m:
            logger.warning(
                "workday: keyword %r does not match a Workday careers-site spec "
                "(<tenant>.<dc>.myworkdayjobs.com/<site>); skipping",
                keyword,
            )
            return empty

        host: str = m.group("host").lower()
        tenant: str = m.group("tenant").lower()
        site: str = m.group("site").rstrip("/")
        token = f"{host}/{site}"

        # Politeness throttle — skip if we fetched this token recently
        now = time.monotonic()
        if token in _last_fetch:
            elapsed = now - _last_fetch[token]
            if elapsed < WORKDAY_MIN_INTERVAL_S:
                logger.info(
                    "workday: throttled %r (last fetch %.0fs ago, min interval %ds)",
                    token, elapsed, WORKDAY_MIN_INTERVAL_S,
                )
                return empty

        applied: dict[str, list[str]] = {}
        search = WORKDAY_SEARCH_TEXT
        max_pages = max(1, WORKDAY_MAX_PAGES)
        try:
            if WORKDAY_COUNTRY:
                probe = _fetch(host, tenant, site, search, limit=1)
                applied = country_facets(probe.get("facets") or [], WORKDAY_COUNTRY)
                if not applied:
                    _last_fetch[token] = time.monotonic()
                    logger.info("workday: %r has no %s filter; nothing to fetch",
                                token, WORKDAY_COUNTRY)
                    return empty
                time.sleep(WORKDAY_PAGE_DELAY_S)
            else:
                search, max_pages = "", 1  # legacy: newest postings worldwide
            data = _fetch(host, tenant, site, search, applied_facets=applied, offset=0)
        except Exception:  # noqa: BLE001
            logger.warning("workday: fetch failed for %r", token, exc_info=True)
            return empty

        _last_fetch[token] = time.monotonic()

        found = 0
        new = 0
        jobs: list[dict[str, Any]] = []
        total = int(data.get("total") or 0)
        page = 0

        while True:
            postings: list[dict[str, Any]] = data.get("jobPostings") or []
            for item in postings:
                try:
                    title: str | None = item.get("title")
                    if not title:
                        continue
                    loc: str = item.get("locationsText") or location
                    external_path: str = item.get("externalPath") or ""
                    apply_url = f"https://{host}/{site}{external_path}"
                    sid = external_path
                    posted: str | None = item.get("postedOn")
                    bullet_fields: list[Any] = item.get("bulletFields") or []
                    snippet = (
                        f"{title} — {loc}\n" + " · ".join(str(b) for b in bullet_fields)
                    ).strip()

                    found += 1
                    jobs.append(
                        {"title": title, "company": tenant, "location": loc,
                         "apply_url": apply_url}
                    )
                    if dry_run:
                        continue
                    if persist_full_jd_job(
                        source="workday",
                        source_job_id=str(sid),
                        title=title,
                        company=tenant,
                        location=loc,
                        full_jd=snippet,
                        apply_url=apply_url,
                        posted_date=posted,
                        raw_payload={},
                    ):
                        new += 1
                except Exception:  # noqa: BLE001
                    logger.warning("workday: failed to parse item %r", item, exc_info=True)
                    continue

            page += 1
            offset = page * _PAGE_SIZE
            if page >= max_pages or not postings or offset >= total:
                break
            time.sleep(WORKDAY_PAGE_DELAY_S)
            try:
                data = _fetch(host, tenant, site, search, applied_facets=applied, offset=offset)
            except Exception:  # noqa: BLE001 — e.g. 429: keep what we have, retry next run
                logger.warning("workday: stopped paging %r at offset %d", token, offset,
                               exc_info=True)
                break

        return {"found": found, "new": new, "jobs": jobs}


register(WorkdaySource())
