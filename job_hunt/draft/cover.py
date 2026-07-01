"""Cover-letter generation — short, specific, grounded in real experience."""
from __future__ import annotations

import json
from typing import Any

from job_hunt.llm.ollama import chat
from job_hunt.llm.prompts import COVER_LETTER


def generate_cover_letter(
    *, jd_text: str, resume_json: dict[str, Any], company: str = "", role: str = ""
) -> str:
    """Return a cover-letter body for a job."""
    prompt = (
        f"Write a cover letter for {role or 'this role'} at {company or 'this company'}.\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{jd_text[:4000]}\n\n"
        "=== CANDIDATE RESUME (structured JSON) ===\n"
        f"{json.dumps(resume_json, ensure_ascii=False)[:3000]}\n\n"
        "Output only the letter body."
    )
    return chat(prompt, task="drafting", system=COVER_LETTER.system, temperature=0.5)
