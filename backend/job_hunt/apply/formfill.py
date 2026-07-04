"""ATS form auto-fill: resolve stored data onto a declarative profile, fill, stop at review.

The engine never submits: it fills every field it can and hands a highlighted (unsubmitted)
form to the human. Fill logic runs against a `FormPage` protocol so it is testable without a
real browser; the Playwright adapter is the production `FormPage`.
"""
from __future__ import annotations

from typing import Any, Protocol

from job_hunt.apply.formfill_profiles import validate_profile
from job_hunt.logging_config import get_logger

logger = get_logger(__name__)


class FormPage(Protocol):
    """Minimal browser-page surface the filler needs (real impl wraps Playwright)."""

    def has(self, selector: str) -> bool: ...
    def fill_text(self, selector: str, value: str) -> None: ...
    def select_option(self, selector: str, value: str) -> None: ...
    def set_file(self, selector: str, path: str) -> None: ...
    def set_checkbox(self, selector: str, checked: bool) -> None: ...
    def highlight(self, selector: str) -> None: ...


def _fill_page(page: FormPage, profile: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Fill every resolvable, present field; collect unfilled required fields; never submit."""
    err = validate_profile(profile)
    if err:
        raise ValueError(f"invalid form profile: {err}")

    filled: list[str] = []
    unfilled: list[str] = []
    for field in profile["fields"]:
        selector = field["selector"]
        value = _resolve(field["source"], data)
        if value is None:
            if not field.get("optional"):
                unfilled.append(selector)
            continue
        if not page.has(selector):
            if not field.get("optional"):
                unfilled.append(selector)
            continue
        kind = field.get("kind", "text")
        if kind == "file":
            page.set_file(selector, value)
        elif kind == "select":
            page.select_option(selector, value)
        elif kind == "checkbox":
            page.set_checkbox(selector, value.lower() in ("true", "yes", "1"))
        else:
            page.fill_text(selector, value)
        filled.append(selector)

    submit = profile.get("submit") or {}
    if submit.get("selector") and page.has(submit["selector"]):
        page.highlight(submit["selector"])  # highlight only — never click
    return {"filled": filled, "unfilled": unfilled}


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
