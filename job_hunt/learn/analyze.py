"""Rejection-gap analysis — what the resume under-emphasized for a JD."""
from __future__ import annotations

import json
from typing import Any

from job_hunt.llm.ollama import chat_json
from job_hunt.llm.prompts import REJECTION_GAP


def analyze_rejection(*, jd_text: str, resume_json: dict[str, Any]) -> dict[str, Any]:
    """Return {missing_keywords: [...], summary: str} for a rejected application."""
    prompt = (
        "Analyze this rejected application: what did the resume under-emphasize vs the JD?\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{jd_text[:5000]}\n\n"
        "=== CANDIDATE RESUME (structured JSON) ===\n"
        f"{json.dumps(resume_json, ensure_ascii=False)[:4000]}\n\n"
        'Return JSON: {"missing_keywords": [...], "summary": "..."}.'
    )
    return chat_json(
        prompt, schema=REJECTION_GAP.schema, task="drafting",
        system=REJECTION_GAP.system, temperature=0.2,
    )
