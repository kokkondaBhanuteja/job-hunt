"""Canonical cross-source dedup key — shared by every source plugin.

`dedup_hash(company, title, location)` is the identity of a role regardless of which
board surfaced it, so a Naukri listing and a RemoteOK listing for the same job collapse
to one row (but the same title in two cities stays distinct).
"""
from __future__ import annotations

import hashlib
import re

_SLUG = re.compile(r"[^a-z0-9]+")
_SENIORITY = re.compile(r"\b(sr|sr\.|senior|jr|jr\.|junior|lead|principal|staff)\b")


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")


def _normalize_title(title: str) -> str:
    """Strip seniority/level fluff so the same role from different sources dedupes."""
    s = _SENIORITY.sub("", title.lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def dedup_hash(company: str, title: str, location: str = "") -> str:
    """Canonical dedup key: `company | normalized-title | location`.

    Location defaults to "" so two-arg callers keep their old behavior.
    """
    key = f"{_slug(company)}|{_normalize_title(title)}|{_slug(location or '')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()
