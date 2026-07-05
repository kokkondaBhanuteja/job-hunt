"""Naukri profile-refresh helper — draft-only, zero browser interaction.

Drafts an optimized Naukri headline, professional summary, and skills list
from the candidate's career context + best résumé variant, then sends the
draft to the user's configured notification channel so they can paste it
manually into their Naukri profile.

This module MUST NOT import any browser, login, or automation code.
It only drafts text and notifies the user.
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.llm.client import chat_json
from job_hunt.llm.prompts import PROFILE_REFRESH
from job_hunt.logging_config import get_logger
from job_hunt.notify.base import get_notifier
from job_hunt.services.context import context_preamble
from job_hunt.storage import repo

logger = get_logger(__name__)


def draft_profile_refresh() -> dict[str, Any]:
    """Draft an optimized Naukri headline, summary, and skills list.

    Return {headline, summary, skills} on success, or {"error": <message>} when
    the required context or résumé data is not yet set up.
    """
    repo.init_db()

    preamble = context_preamble()
    if not preamble:
        return {"error": "no career context set — run `hunt context <file>` first"}

    variants = repo.list_resume_variants()
    if not variants:
        return {"error": "no résumé variants found — run `hunt parse-resume` first"}

    # Use the first variant (best available without a scored job reference).
    variant = variants[0]
    try:
        resume_json: dict[str, Any] = json.loads(variant["parsed_json"])
    except (KeyError, TypeError, ValueError):
        resume_json = {}

    prompt = (
        f"{preamble}"
        f"Résumé data (JSON):\n{json.dumps(resume_json, indent=2)}\n\n"
        "Draft the Naukri profile headline, summary, and skills list. "
        "Output JSON only."
    )

    result: dict[str, Any] = chat_json(
        prompt,
        schema=PROFILE_REFRESH.schema,
        task="drafting",
        system=PROFILE_REFRESH.system,
        prompt_name=PROFILE_REFRESH.name,
        prompt_version=PROFILE_REFRESH.version,
    )
    return result


def refresh_reminder() -> None:
    """Scheduled entrypoint: draft the profile and notify the user. Never raises."""
    try:
        result = draft_profile_refresh()
        if "error" in result:
            logger.warning("naukri_refresh skipped: %s", result["error"])
            return
        headline: str = result.get("headline", "")
        summary: str = result.get("summary", "")
        get_notifier().send(
            f"\U0001f504 Time to refresh your Naukri profile — paste this:\n\n"
            f"Headline: {headline}\n\n"
            f"Summary: {summary}"
        )
        logger.info("naukri_refresh: draft sent to notifier")
    except Exception:  # noqa: BLE001
        logger.exception("naukri_refresh: unexpected error — skipping")
