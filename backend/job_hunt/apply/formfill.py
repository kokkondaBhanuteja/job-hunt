"""ATS form auto-fill: resolve stored data onto a declarative profile, fill, stop at review.

The engine never submits: it fills every field it can and hands a highlighted (unsubmitted)
form to the human. Fill logic runs against a `FormPage` protocol so it is testable without a
real browser; the async production path uses `managed_context` (real Playwright) and blocks
until the human closes the tab.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol

from job_hunt.apply.answerer import draft_answers
from job_hunt.apply.ats import detect_ats
from job_hunt.apply.formfill_profiles import load_profile, validate_profile
from job_hunt.browser import managed_context
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
        value = str(value)
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

    best = repo.best_scored_variant(int(job["id"]))
    if best is None:
        variants = repo.list_resume_variants()
        best = variants[0] if variants else None
    resume: dict[str, Any] = {}
    resume_path: str | None = None
    if best is not None:
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
        "jd": job["description_full"] or job["description"] or "",
    }


async def _fill_page_async(
    page: Any, profile: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any]:
    """Fill every resolvable field via the async Playwright page API; never submit."""
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
        if await page.query_selector(selector) is None:
            if not field.get("optional"):
                unfilled.append(selector)
            continue
        value = str(value)
        kind = field.get("kind", "text")
        if kind == "file":
            await page.set_input_files(selector, value)
        elif kind == "select":
            await page.select_option(selector, label=value)
        elif kind == "checkbox":
            await page.set_checked(selector, value.lower() in ("true", "yes", "1"))
        else:
            await page.fill(selector, value)
        filled.append(selector)

    submit = profile.get("submit") or {}
    if submit.get("selector") and await page.query_selector(submit["selector"]) is not None:
        await page.eval_on_selector(
            submit["selector"], "el => el.style.outline='3px solid #16A34A'"
        )

    return {"filled": filled, "unfilled": unfilled}


async def _discover_questions(page: Any) -> list[dict[str, Any]]:
    """Best-effort DOM scrape for unfilled visible text fields and their label text."""
    try:
        return await page.evaluate(
            """() => {
                const results = [];
                const els = [...document.querySelectorAll('textarea, input[type="text"]')];
                for (const el of els) {
                    if (el.value && el.value.trim()) continue;
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') continue;
                    if (!el.offsetParent) continue;
                    let label = '';
                    if (el.id) {
                        const lbl = document.querySelector('label[for="' + el.id + '"]');
                        if (lbl) label = lbl.textContent.trim();
                    }
                    if (!label) {
                        let p = el.parentElement;
                        while (p && p.tagName !== 'LABEL') p = p.parentElement;
                        if (p) label = p.textContent.trim();
                    }
                    if (!label) {
                        label = el.getAttribute('aria-label')
                            || el.getAttribute('placeholder')
                            || el.name
                            || '';
                    }
                    if (!label) continue;
                    let selector = '';
                    if (el.id) {
                        selector = '#' + CSS.escape(el.id);
                    } else if (el.name) {
                        selector = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                    } else {
                        const all = [...document.querySelectorAll(el.tagName.toLowerCase())];
                        selector = el.tagName.toLowerCase() + ':nth-of-type(' + (all.indexOf(el) + 1) + ')';
                    }
                    results.push({ question: label, selector: selector, kind: 'text' });
                }
                return results;
            }"""
        )
    except Exception:  # noqa: BLE001 — defensive; a broken ATS page must not abort the fill
        logger.debug("_discover_questions failed; skipping screening-question fill", exc_info=True)
        return []


async def _fill_via_browser(url: str, profile: dict[str, Any], data: dict[str, Any], ats: str) -> dict[str, Any]:
    """Open `url` in a headful Chromium context, fill the form, block until the human closes the tab."""
    async with managed_context("formfill", headless=False) as ctx:
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        summary = await _fill_page_async(page, profile, data)

        # Discover and fill any remaining screening questions via LLM
        try:
            found = await _discover_questions(page)
            if found:
                answers = draft_answers(
                    [q["question"] for q in found],
                    jd_text=data.get("jd") or "",
                    resume_json=data.get("resume") or {},
                    applicant=data.get("applicant") or {},
                    context=data.get("context") or "",
                )
                for item in found:
                    answer = answers.get(item["question"])
                    if answer:
                        await page.fill(item["selector"], answer)
                logger.info("screening questions filled: %d answered", len(answers))
        except Exception:  # noqa: BLE001 — never break the fill or auto-submit on error
            logger.warning("screening-question fill failed; proceeding to review", exc_info=True)

        logger.info("form filled — review in the browser, submit, then close the tab")
        await page.wait_for_event("close", timeout=0)  # block until the human closes the tab
        return {"ats": ats, "review_url": url, **summary}


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
    if page_factory is not None:
        page = page_factory(job["apply_url"])
        summary = _fill_page(page, profile, data)
        return {"ats": ats, "review_url": job["apply_url"], **summary}
    return asyncio.run(_fill_via_browser(job["apply_url"], profile, data, ats))
