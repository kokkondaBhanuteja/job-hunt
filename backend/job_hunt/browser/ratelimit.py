"""Per-source rate limiting — independent limits per platform (LinkedIn ≠ Naukri).

A minimal monotonic-clock limiter: enforce a minimum interval between actions
keyed by source. The clock is injectable so the logic is unit-testable without
real sleeps.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        min_interval_s: float = 2.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.min_interval_s = min_interval_s
        self._clock = clock
        self._last: dict[str, float] = {}

    def seconds_until_ready(self, key: str) -> float:
        """How long the caller must wait before acting on `key` again (0 if ready)."""
        last = self._last.get(key)
        if last is None:
            return 0.0
        return max(0.0, self.min_interval_s - (self._clock() - last))

    def record(self, key: str) -> None:
        """Mark `key` as just-used (resets its interval)."""
        self._last[key] = self._clock()

    async def acquire(self, key: str) -> None:
        """Wait until `key` is ready, then record the action."""
        wait = self.seconds_until_ready(key)
        if wait > 0:
            await asyncio.sleep(wait)
        self.record(key)
