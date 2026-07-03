"""Pure pacing helpers — active-hours window + per-day cap.

Time is passed in (hour, minute) so the logic is deterministic and unit-testable
without touching the clock.
"""
from __future__ import annotations


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def within_active_hours(hour: int, minute: int, *, start: str, end: str) -> bool:
    """True if (hour:minute) falls in [start, end). Handles windows past midnight."""
    now = hour * 60 + minute
    start_m, end_m = _to_minutes(start), _to_minutes(end)
    if start_m <= end_m:
        return start_m <= now < end_m
    # Wraps midnight, e.g. 22:00 → 06:00.
    return now >= start_m or now < end_m


def cap_reached(submitted_today: int, cap: int) -> bool:
    """True once the day's submission cap is hit (the worker then stops queueing)."""
    return submitted_today >= cap
