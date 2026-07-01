"""Scrape-health classification.

A run that scrapes 0 jobs because of a captcha looks identical to "no new jobs"
unless we distinguish them. `classify_scrape` turns (cards found, blocked signal,
expectation) into an explicit status so the worker can fail a blocked run loudly
instead of silently reporting "nothing new".
"""
from __future__ import annotations

from job_hunt.enums import ScrapeStatus


def classify_scrape(
    found_cards: int,
    *,
    blocked_signal: bool = False,
    expected_min: int = 1,
) -> ScrapeStatus:
    """Classify a scrape pass.

    Args:
        found_cards: how many job cards were extracted.
        blocked_signal: True if a login-wall / captcha element was detected.
        expected_min: minimum cards we'd expect on a healthy results page.

    Returns:
        BLOCKED if challenged, EMPTY if we found fewer than expected (suspicious),
        else OK.
    """
    if blocked_signal:
        return ScrapeStatus.BLOCKED
    if found_cards < expected_min:
        return ScrapeStatus.EMPTY
    return ScrapeStatus.OK
