"""Managed Playwright contexts + a shared browser fingerprint.

`managed_context(site)` yields a stealthed persistent context using one profile
per site under data/sessions/<site>/. Centralizes the launch options that were
duplicated across sources/naukri.py and sources/login.py.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from random import uniform
from typing import AsyncIterator

from playwright.async_api import BrowserContext, async_playwright
from playwright_stealth import Stealth

from job_hunt.browser.ratelimit import RateLimiter

# One shared per-source limiter — the Manager owns pacing, so every scraper is throttled
# by the same minimum interval per site (LinkedIn ≠ Naukri). Wired into the crawlers.
_RATE_LIMITER = RateLimiter(min_interval_s=float(os.getenv("SCRAPE_MIN_INTERVAL_S", "2.0")))


def rate_limiter() -> RateLimiter:
    """The process-wide per-source rate limiter."""
    return _RATE_LIMITER

# One stable fingerprint everywhere (principle #9: no churn). Keep current.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1440, "height": 900}
LOCALE = "en-IN"
TIMEZONE = "Asia/Kolkata"

SESSIONS_BASE = Path(__file__).resolve().parents[2] / "data" / "sessions"


def session_dir(site: str) -> Path:
    """Persistent-profile directory for a site (cookies/localStorage live here)."""
    return SESSIONS_BASE / site


@asynccontextmanager
async def managed_context(
    site: str, *, headless: bool = False
) -> AsyncIterator[BrowserContext]:
    """Yield a stealthed persistent Chromium context for `site`.

    Closes the context on exit. RPA-style (headed) by default — more reliable;
    pass headless=True only once the session is warm.
    """
    profile = session_dir(site)
    profile.mkdir(parents=True, exist_ok=True)

    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
            locale=LOCALE,
            timezone_id=TIMEZONE,
        )
        try:
            yield ctx
        finally:
            try:
                await ctx.close()
            except Exception:  # noqa: BLE001 — user may have already closed the window
                pass


async def human_pause(lo: float = 0.6, hi: float = 1.4) -> None:
    """Sleep a randomized, human-ish interval (principle #1: no robotic cadence)."""
    await asyncio.sleep(uniform(lo, hi))
