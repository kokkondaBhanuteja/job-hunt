"""Detect the ATS behind a job's apply URL — chooses the per-platform apply flow.

Different ATSes (Greenhouse, Lever, Workday, …) render forms differently, so the
apply subsystem branches on this. Detection is a pure host/path match — no network.
"""
from __future__ import annotations

from urllib.parse import urlparse

from job_hunt.enums import ATSPlatform

# host substring → platform. Ordered by specificity; first match wins.
_HOST_PATTERNS: list[tuple[str, ATSPlatform]] = [
    ("greenhouse.io", ATSPlatform.GREENHOUSE),
    ("lever.co", ATSPlatform.LEVER),
    ("myworkdayjobs.com", ATSPlatform.WORKDAY),
    ("workday.com", ATSPlatform.WORKDAY),
    ("ashbyhq.com", ATSPlatform.ASHBY),
    ("smartrecruiters.com", ATSPlatform.SMARTRECRUITERS),
    ("icims.com", ATSPlatform.ICIMS),
    ("naukri.com", ATSPlatform.NAUKRI),
    ("remoteok.com", ATSPlatform.REMOTEOK),
    ("remoteok.io", ATSPlatform.REMOTEOK),
]


def detect_ats(apply_url: str | None) -> ATSPlatform:
    """Return the ATS platform for an apply URL, or UNKNOWN."""
    if not apply_url:
        return ATSPlatform.UNKNOWN
    host = (urlparse(apply_url).hostname or apply_url).lower()
    for needle, platform in _HOST_PATTERNS:
        if needle in host:
            return platform
    return ATSPlatform.UNKNOWN
