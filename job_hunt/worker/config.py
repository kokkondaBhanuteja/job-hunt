"""Worker config — pacing guardrails + schedule intervals (env-overridable)."""
from __future__ import annotations

import os

# Anti-detection pacing (principles #11, #1): only act in realistic local hours,
# and cap submissions per day. Times are local "HH:MM".
ACTIVE_START = os.getenv("WORKER_ACTIVE_START", "09:30")
ACTIVE_END = os.getenv("WORKER_ACTIVE_END", "21:00")
DAILY_CAP = int(os.getenv("WORKER_DAILY_CAP", "30"))

# Schedule cadence.
DISCOVERY_INTERVAL_MIN = int(os.getenv("WORKER_DISCOVERY_INTERVAL_MIN", "180"))
DISPATCH_INTERVAL_SEC = int(os.getenv("WORKER_DISPATCH_INTERVAL_SEC", "30"))
