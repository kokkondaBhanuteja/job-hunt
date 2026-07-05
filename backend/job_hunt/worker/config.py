"""Worker config — pacing guardrails + schedule intervals (env-overridable)."""
from __future__ import annotations

import os

# Anti-detection pacing: only act in realistic local hours, and cap discovery runs per
# day (enforced in runner.run_all_active_profiles; the same cap will gate submissions once
# live form-fill lands). Times are local "HH:MM".
ACTIVE_START = os.getenv("WORKER_ACTIVE_START", "09:30")
ACTIVE_END = os.getenv("WORKER_ACTIVE_END", "21:00")
DAILY_CAP = int(os.getenv("WORKER_DAILY_CAP", "30"))

# Schedule cadence.
DISCOVERY_INTERVAL_MIN = int(os.getenv("WORKER_DISCOVERY_INTERVAL_MIN", "180"))
DISPATCH_INTERVAL_SEC = int(os.getenv("WORKER_DISPATCH_INTERVAL_SEC", "30"))

# API source discovery (cheap httpx sources — no browser, no active-hours gate).
API_DISCOVERY_INTERVAL_MIN = int(os.getenv("WORKER_API_DISCOVERY_INTERVAL_MIN", "20"))
# remotive excluded from default: terms cap ≤4 calls/day, too slow for this loop.
API_SOURCES = [
    s.strip()
    for s in os.getenv(
        "WORKER_API_SOURCES",
        "remoteok,adzuna,weworkremotely,workingnomads,jobspresso",
    ).split(",")
    if s.strip()
]
