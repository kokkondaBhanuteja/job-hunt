"""
Naukri.com scraper. The riskiest piece in the whole toolkit because:
- Selectors change every few months
- They have anti-bot detection
- Login is needed for some details

v0 design: scrape the PUBLIC listing pages (no login) with a persisted Playwright
profile that you can log into manually if/when needed. We only grab what's on the
listing card (title, company, location, snippet, apply URL). Full JD enrichment
can come in v1.

Selectors are loaded from config/selectors/naukri.json so you can hot-patch them
when Naukri reshuffles their CSS classes — no Python edit needed.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from job_hunt.browser import human_pause, managed_context
# Canonical dedup helpers are shared across sources; re-exported here so existing
# imports (`from job_hunt.sources.naukri import dedup_hash`) keep working.
from job_hunt.sources.dedup import _normalize_title, _slug, dedup_hash  # noqa: F401
from job_hunt.states import mark_discovered
from job_hunt.storage.repo import insert_job_if_new

# ---------- Paths / config ----------

SELECTOR_FILE = Path(__file__).resolve().parents[2] / "config" / "selectors" / "naukri.json"

DEFAULT_SELECTORS: dict[str, str] = {
    # Naukri's layout nests cust-job-tuple INSIDE srp-jobtuple-wrapper on each
    # card. Match only the inner one to avoid double-extracting every job.
    # Hot-patch via config/selectors/naukri.json if the layout changes.
    "card":     "div.cust-job-tuple",
    "title":    "a.title",
    "company":  "a.comp-name, span.comp-name",
    "location": "span.locWdth, span.loc-wrap",
    "snippet":  "span.job-desc",
    "experience": "span.expwdth, span.exp-wrap",
    "posted":   "span.job-post-day, span.post-day",
}


def _load_selectors() -> dict[str, str]:
    """Read selectors from config file if present, fall back to defaults."""
    if SELECTOR_FILE.exists():
        try:
            data = json.loads(SELECTOR_FILE.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_SELECTORS)
            merged.update(data)
            return merged
        except json.JSONDecodeError:
            pass
    return dict(DEFAULT_SELECTORS)


# ---------- Helpers ----------


def build_search_url(keyword: str, location: str, page: int = 1) -> str:
    """Naukri's URL pattern: /<keyword>-jobs-in-<location>?<...>"""
    k = _slug(keyword)
    loc = _slug(location)
    base = f"https://www.naukri.com/{k}-jobs-in-{loc}"
    return f"{base}-{page}" if page > 1 else base


# ---------- Job extraction ----------


@dataclass
class JobCard:
    title: str
    company: str
    location: str | None
    apply_url: str
    snippet: str | None
    experience: str | None
    posted: str | None


async def _scroll_to_load_more(page: Page, *, pixels_per_step: int = 800) -> None:
    """Naukri lazy-loads cards as you scroll. Walk to the bottom."""
    last_height = 0
    for _ in range(10):
        current_height = await page.evaluate("document.body.scrollHeight")
        if current_height == last_height:
            break
        await page.evaluate(f"window.scrollBy(0, {pixels_per_step})")
        await human_pause()
        last_height = current_height


async def _extract_cards(page: Page, selectors: dict[str, str]) -> list[JobCard]:
    """Pull every job-card from the current listing page."""
    cards: list[JobCard] = []

    locator = page.locator(selectors["card"])
    count = await locator.count()
    for i in range(count):
        card = locator.nth(i)
        try:
            title_el = card.locator(selectors["title"]).first
            title = (await title_el.inner_text()).strip()
            apply_url = await title_el.get_attribute("href") or ""

            company = await _safe_text(card, selectors["company"])
            location = await _safe_text(card, selectors["location"])
            snippet = await _safe_text(card, selectors["snippet"])
            experience = await _safe_text(card, selectors["experience"])
            posted = await _safe_text(card, selectors["posted"])

            if not title or not apply_url:
                continue

            cards.append(
                JobCard(
                    title=title,
                    company=company or "Unknown",
                    location=location,
                    apply_url=apply_url,
                    snippet=snippet,
                    experience=experience,
                    posted=posted,
                )
            )
        except Exception:
            # One bad card shouldn't kill the whole crawl.
            continue
    return cards


async def _safe_text(card: Any, selector: str) -> str | None:
    """inner_text that survives missing elements."""
    try:
        el = card.locator(selector).first
        if await el.count() == 0:
            return None
        return (await el.inner_text()).strip()
    except Exception:
        return None


# ---------- Public API ----------


async def crawl(
    keyword: str,
    location: str,
    *,
    pages: int = 1,
    dry_run: bool = False,
    headless: bool = False,
) -> dict[str, Any]:
    """Crawl Naukri for (keyword, location). Persists new jobs to SQLite.

    RPA-style by default: opens a real Chrome window using the persisted profile
    at data/sessions/naukri/. Run `hunt login naukri` once to sign in — the
    cookies last weeks. Override with `headless=True` only after you've confirmed
    the session is warm and Naukri isn't challenging it.

    Args:
        keyword: e.g. "nestjs backend"
        location: e.g. "bangalore"
        pages:   how many listing pages to walk
        dry_run: if True, do NOT write to SQLite — just return what was found
        headless: default False. RPA is more reliable when you can SEE it work.

    Returns:
        {found: int, new: int, jobs: [JobCard...]}
    """
    selectors = _load_selectors()
    found: list[JobCard] = []
    new_count = 0

    # Browser Manager owns the stealthed persistent profile + fingerprint.
    async with managed_context("naukri", headless=headless) as ctx:
        page = await ctx.new_page()
        for page_no in range(1, pages + 1):
            url = build_search_url(keyword, location, page=page_no)
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            # Wait for at least one card OR timeout — Naukri sometimes renders
            # an empty results page when blocked.
            try:
                await page.wait_for_selector(selectors["card"], timeout=20_000)
            except Exception:
                # Could be: 0 results, OR blocked. Log + move on.
                continue

            await _scroll_to_load_more(page)
            cards = await _extract_cards(page, selectors)
            found.extend(cards)

            # Human-ish pause between pages
            await human_pause(1.8, 3.2)

    if not dry_run:
        for c in found:
            inserted = insert_job_if_new(
                dedup_hash=dedup_hash(c.company, c.title, c.location or ""),
                source="naukri",
                source_job_id=None,
                title=c.title,
                company=c.company,
                location=c.location,
                description=c.snippet,         # v0: snippet only; v1 enriches full JD
                apply_url=c.apply_url,
                posted_date=c.posted,
                raw_payload={
                    "experience": c.experience,
                    "snippet": c.snippet,
                },
            )
            if inserted is not None:
                new_count += 1
                try:
                    mark_discovered(inserted)
                except Exception:  # noqa: BLE001 — never let bookkeeping break a crawl
                    pass

    return {
        "found": len(found),
        "new": new_count,
        "jobs": [c.__dict__ for c in found],
    }


def crawl_sync(
    keyword: str,
    location: str,
    *,
    pages: int = 1,
    dry_run: bool = False,
    headless: bool = True,
) -> dict[str, Any]:
    """Sync wrapper — handy for the CLI and for the MCP server."""
    return asyncio.run(
        crawl(keyword, location, pages=pages, dry_run=dry_run, headless=headless)
    )


# ---------- JD enrichment ----------

# Naukri's JD container class churns; try a few, then fall back to body text.
JD_SELECTORS = [
    "div.styles_JDC__dang-inner-html__h0K4t",
    "section.job-desc",
    "div.dang-inner-html",
    "div.job-description",
    "div.jd-container",
]


async def fetch_job_description(apply_url: str, *, headless: bool = True) -> str | None:
    """Open a Naukri job page and extract the full JD text (or None)."""
    async with managed_context("naukri", headless=headless) as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(apply_url, wait_until="domcontentloaded", timeout=45_000)
        except Exception:
            return None
        await human_pause(1.0, 2.0)

        for selector in JD_SELECTORS:
            try:
                el = page.locator(selector).first
                if await el.count():
                    text = (await el.inner_text()).strip()
                    if len(text) > 200:  # a real JD, not a stub element
                        return text
            except Exception:
                continue
        try:  # fallback: whole page text, capped
            return (await page.locator("body").inner_text()).strip()[:8000] or None
        except Exception:
            return None


def fetch_job_description_sync(apply_url: str, *, headless: bool = True) -> str | None:
    return asyncio.run(fetch_job_description(apply_url, headless=headless))
