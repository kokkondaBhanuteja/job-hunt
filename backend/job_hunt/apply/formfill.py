"""ATS form auto-fill: resolve stored data onto a declarative profile, fill, stop at review.

The engine never submits: it fills every field it can and hands a highlighted (unsubmitted)
form to the human. Fill logic runs against a `FormPage` protocol so it is testable without a
real browser; the Playwright adapter is the production `FormPage`.
"""
from __future__ import annotations

from typing import Any


def _resolve(source: str, data: dict[str, Any]) -> str | None:
    """Resolve a profile field's `source` string to a value, or None if unavailable."""
    if source == "context":
        return data.get("context") or None
    if source == "draft.cover":
        return (data.get("draft") or {}).get("cover") or None
    if source == "file.resume_variant":
        return (data.get("file") or {}).get("resume_variant") or None
    if "." not in source:
        return None
    ns, key = source.split(".", 1)
    if ns == "applicant":
        applicant = data.get("applicant") or {}
        if key == "full_name":
            parts = [applicant.get("first_name"), applicant.get("last_name")]
            joined = " ".join(p for p in parts if p)
            return joined or None
        return applicant.get(key) or None
    if ns == "resume":
        return (data.get("resume") or {}).get(key) or None
    return None
