"""Tests for the Browser Manager's pure logic (rate limiter, health, session paths)."""
from __future__ import annotations

from job_hunt.browser import RateLimiter, classify_scrape, session_dir
from job_hunt.enums import ScrapeStatus


def test_rate_limiter_enforces_min_interval_with_injected_clock():
    now = {"t": 0.0}
    rl = RateLimiter(min_interval_s=2.0, clock=lambda: now["t"])

    # First use is always ready.
    assert rl.seconds_until_ready("naukri") == 0.0
    rl.record("naukri")

    # 1s later, still 1s to wait.
    now["t"] = 1.0
    assert rl.seconds_until_ready("naukri") == 1.0
    # A different source is independent.
    assert rl.seconds_until_ready("linkedin") == 0.0

    # Past the interval → ready again.
    now["t"] = 2.5
    assert rl.seconds_until_ready("naukri") == 0.0


def test_classify_scrape_distinguishes_blocked_empty_ok():
    assert classify_scrape(0, blocked_signal=True) == ScrapeStatus.BLOCKED
    assert classify_scrape(0) == ScrapeStatus.EMPTY
    assert classify_scrape(20) == ScrapeStatus.OK
    # Fewer than expected is suspicious.
    assert classify_scrape(2, expected_min=5) == ScrapeStatus.EMPTY


def test_session_dir_is_per_site_under_data_sessions():
    p = session_dir("naukri")
    assert p.name == "naukri"
    assert p.parent.name == "sessions"
