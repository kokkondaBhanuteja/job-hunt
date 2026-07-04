"""ATS form auto-fill: resolve stored data onto a declarative profile, fill, stop at review.

The engine never submits: it fills every field it can and hands a highlighted (unsubmitted)
form to the human. Fill logic runs against a `FormPage` protocol so it is testable without a
real browser; the Playwright adapter is the production `FormPage`.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from job_hunt.apply.ats import detect_ats
from job_hunt.apply.formfill_profiles import load_profile, validate_profile
from job_hunt.logging_config import get_logger
from job_hunt.storage import repo

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


def _gather_data(job: Any) -> dict[str, Any]:
    """Assemble the data bundle a form profile resolves against for one job."""
    from job_hunt.services.context import context_preamble  # local: avoid import cycle

    applicant_row = repo.get_applicant_profile()
    applicant = dict(applicant_row) if applicant_row else {}

    variants = repo.list_resume_variants()
    resume: dict[str, Any] = {}
    resume_path: str | None = None
    if variants:
        best = variants[0]
        resume = json.loads(best["parsed_json"]) if best["parsed_json"] else {}
        resume_path = best["source_path"]

    cover = None
    drafts = repo.list_drafts_for_job(int(job["id"])) if hasattr(repo, "list_drafts_for_job") else []
    for d in drafts:
        if d["kind"] == "cover":
            cover = d["body"]
            break

    return {
        "applicant": applicant,
        "resume": resume,
        "context": context_preamble() or None,
        "draft": {"cover": cover},
        "file": {"resume_variant": resume_path},
    }


def prepare_form_fill(
    job_id: int, *, page_factory: Callable[[str], FormPage] | None = None
) -> dict[str, Any]:
    """Open a job's ATS form, fill what we can, stop at review. Return a summary or {error}."""
    repo.init_db()
    job = repo.get_job(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    ats = str(detect_ats(job["apply_url"]))
    profile = load_profile(ats)
    if profile is None:
        return {"error": f"no form profile for '{ats}' yet"}

    data = _gather_data(job)
    factory = page_factory or _playwright_page_factory
    page = factory(job["apply_url"])
    summary = _fill_page(page, profile, data)
    return {"ats": ats, "review_url": job["apply_url"], **summary}


def _playwright_page_factory(url: str) -> FormPage:
    """Open `url` in the managed (headful) browser and return a Playwright-backed FormPage.

    CONCERN: managed_context is an async context manager. This sync wrapper acquires the
    context via __aenter__ but never calls __aexit__, so the browser context is leaked.
    Future task: make prepare_form_fill fully async so the context can be properly closed
    via 'async with managed_context(...)'.
    """
    import asyncio

    from job_hunt.browser.manager import managed_context

    async def _acquire() -> FormPage:
        # Deliberately bypass 'async with' so the page remains live after this coroutine.
        ctx = await managed_context("formfill", headless=False).__aenter__()
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        return _PlaywrightPage(page)

    return asyncio.get_event_loop().run_until_complete(_acquire())


class _PlaywrightPage:
    """FormPage backed by a live Playwright page. Fills fields; never clicks submit."""

    def __init__(self, page: Any):
        self._page = page

    def has(self, selector: str) -> bool:
        """Return True if the selector matches at least one element on the page."""
        return self._page.query_selector(selector) is not None

    def fill_text(self, selector: str, value: str) -> None:
        """Type `value` into the element matching `selector`."""
        self._page.fill(selector, value)

    def select_option(self, selector: str, value: str) -> None:
        """Select the <option> with label `value` in the <select> at `selector`."""
        self._page.select_option(selector, label=value)

    def set_file(self, selector: str, path: str) -> None:
        """Attach local file `path` to the file-input at `selector`."""
        self._page.set_input_files(selector, path)

    def set_checkbox(self, selector: str, checked: bool) -> None:
        """Set the checked state of the checkbox at `selector`."""
        self._page.set_checked(selector, checked)

    def highlight(self, selector: str) -> None:
        """Outline the element at `selector` in green — signals the review boundary."""
        self._page.eval_on_selector(
            selector, "el => el.style.outline = '3px solid #16A34A'"
        )
