"""Location gate for discovered jobs — keep India roles and remote roles open to India.

Watchlist ATS boards return a company's whole worldwide board and remote job sites list
many "US only" roles. Filtering here, before a job is stored, keeps those out of scoring
(LLM quota) and out of the alerts. Controlled by ``JOB_LOCATION_FILTER``:
``india-remote`` (default) or ``off``.
"""
from __future__ import annotations

import os
import re

JOB_LOCATION_FILTER = os.getenv("JOB_LOCATION_FILTER", "india-remote").strip().lower()

_INDIA = re.compile(
    r"\b(india|indian|bengaluru|bangalore|hyderabad|secunderabad|pune|mumbai|navi mumbai|"
    r"chennai|delhi|new delhi|ncr|gurgaon|gurugram|noida|kolkata|ahmedabad|kochi|cochin|"
    r"trivandrum|thiruvananthapuram|jaipur|coimbatore|chandigarh|indore|vadodara|"
    r"visakhapatnam|vizag|warangal|mysore|mysuru|mangalore|bhubaneswar|nagpur|surat|"
    r"lucknow|goa)\b",
    re.IGNORECASE,
)
_REMOTE = re.compile(r"\b(remote|anywhere|worldwide|global|globally|wfh|work from home)\b",
                     re.IGNORECASE)
# Words that may accompany "remote" without restricting it to a non-Indian region.
_FILLER = re.compile(
    r"\b(remote|anywhere|worldwide|global|globally|fully|100%|wfh|work from home|in|the|world|"
    r"apac|asia|pacific|friendly|first|based|location|locations|any|"
    r"timezone|timezones|time zone|time zones|ok|okay|option|optional|hybrid|or|and|team)\b",
    re.IGNORECASE,
)


def is_india_or_open_remote(location: str | None, title: str = "") -> bool:
    """Return True if a job is in India or remote without a non-Indian region restriction."""
    if JOB_LOCATION_FILTER in ("", "off", "none", "all"):
        return True
    text = " ".join(part for part in (location or "", title or "") if part).strip()
    if not (location or "").strip():
        return True  # unknown location: let scoring decide rather than lose the job
    if _INDIA.search(text):
        return True
    loc = location or ""
    if not _REMOTE.search(loc):
        return False  # on-site somewhere outside India
    leftover = re.sub(r"[^a-z]+", " ", _FILLER.sub(" ", loc.lower())).strip()
    return leftover == ""  # e.g. "Remote - US" leaves "us"; "Remote (Worldwide)" leaves ""
