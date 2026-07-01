"""AI pre-submit reviewer — the quality gate before an application is sent.

Runs one LLM pass (via the AI Gateway, `drafting` task so it can be routed to a
stronger model) comparing the resume + cover letter + screening answers against the
JD, and returns a structured verdict {ready, issues[]}. It never submits — a human
still approves in the review queue. Prompt/schema live in the Prompt Library.
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.llm import chat_json
from job_hunt.llm.prompts import APPLICATION_REVIEW


def _build_prompt(
    jd_text: str, resume_json: dict[str, Any], cover_letter: str, answers: dict[str, str]
) -> str:
    return (
        "Review this job application before submission.\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{jd_text[:5000]}\n\n"
        "=== CANDIDATE RESUME (structured) ===\n"
        f"{json.dumps(resume_json, ensure_ascii=False)[:4000]}\n\n"
        "=== COVER LETTER ===\n"
        f"{cover_letter or '(none)'}\n\n"
        "=== SCREENING ANSWERS ===\n"
        f"{json.dumps(answers, ensure_ascii=False) or '(none)'}\n\n"
        'Return JSON: {"ready": bool, "issues": [{"severity","field","message"}]}.'
    )


def review_application(
    *,
    jd_text: str,
    resume_json: dict[str, Any],
    cover_letter: str = "",
    answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return the reviewer's verdict {ready: bool, issues: [...]}."""
    return chat_json(
        _build_prompt(jd_text, resume_json, cover_letter, answers or {}),
        schema=APPLICATION_REVIEW.schema,
        task="drafting",
        system=APPLICATION_REVIEW.system,
        temperature=0.2,
        prompt_name=APPLICATION_REVIEW.name,
        prompt_version=APPLICATION_REVIEW.version,
    )
