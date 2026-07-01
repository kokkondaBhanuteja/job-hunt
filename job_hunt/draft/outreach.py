"""Recruiter-outreach message generation — short, specific, grounded."""
from __future__ import annotations

import json
from typing import Any

from job_hunt.llm import chat
from job_hunt.llm.prompts import OUTREACH


def generate_outreach(
    *, jd_text: str, resume_json: dict[str, Any], company: str = "", role: str = "",
    contact_name: str = "",
) -> str:
    """Return an outreach message body for a job/contact."""
    prompt = (
        f"Write an outreach message to {contact_name or 'the hiring team'} at "
        f"{company or 'the company'} about the {role or 'role'}.\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{jd_text[:3000]}\n\n"
        "=== CANDIDATE RESUME (structured JSON) ===\n"
        f"{json.dumps(resume_json, ensure_ascii=False)[:2500]}\n\n"
        "Output only the message body."
    )
    return chat(prompt, task="drafting", system=OUTREACH.system, temperature=0.5,
                prompt_name=OUTREACH.name, prompt_version=OUTREACH.version)
