"""Browser Manager — the ONLY place Playwright is instantiated.

Owns the single persistent profile per site, stealth, standard fingerprint
(UA/viewport/locale/timezone), per-source rate limiting, humanized pacing, and
scrape-health detection. Every scraper / apply flow borrows a managed context
instead of launching its own — so anti-detection policy lives in one place.
"""
from __future__ import annotations

from job_hunt.browser.health import classify_scrape
from job_hunt.browser.manager import human_pause, managed_context, session_dir
from job_hunt.browser.ratelimit import RateLimiter

__all__ = [
    "managed_context",
    "session_dir",
    "human_pause",
    "RateLimiter",
    "classify_scrape",
]
