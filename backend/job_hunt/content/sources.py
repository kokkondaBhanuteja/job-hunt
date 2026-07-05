"""Content topic sources — real-time fetch from HN Algolia and dev.to APIs.

Module-level `_fetch_hn` and `_fetch_devto` are monkeypatchable in tests.
`top_topics` is the public entry point; it is also module-level so callers can
monkeypatch it directly.
"""
from __future__ import annotations

import httpx

from job_hunt.logging_config import get_logger

logger = get_logger(__name__)

_HN_URL = "http://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=10"
_DEVTO_URL = "https://dev.to/api/articles?top=1&per_page=10"


def _fetch_hn() -> list[dict]:
    """Fetch top Hacker News front-page stories and return simplified dicts."""
    resp = httpx.get(_HN_URL, timeout=30)
    resp.raise_for_status()
    return [
        {
            "title": h["title"],
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
            "snippet": "",
        }
        for h in resp.json()["hits"]
        if h.get("title")
    ]


def _fetch_devto() -> list[dict]:
    """Fetch top dev.to articles and return simplified dicts."""
    resp = httpx.get(_DEVTO_URL, timeout=30)
    resp.raise_for_status()
    return [
        {
            "title": a["title"],
            "url": a["url"],
            "snippet": a.get("description", ""),
        }
        for a in resp.json()
    ]


def top_topics(limit: int = 8) -> list[dict]:
    """Return up to `limit` trending tech topics from HN and dev.to.

    Each topic is {title, url, snippet}. Sources that fail are skipped and logged.
    """
    results: list[dict] = []
    for fetcher in (_fetch_hn, _fetch_devto):
        try:
            results.extend(fetcher())
        except Exception:  # noqa: BLE001 — topic failure must never break drafting
            logger.warning("topic source %s failed", fetcher.__name__, exc_info=True)
    return results[:limit]
