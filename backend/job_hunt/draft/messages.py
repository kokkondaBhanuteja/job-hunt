"""Post-interview message generation — thank-you notes, follow-ups, and negotiation messages."""
from __future__ import annotations

import json
from typing import Any

from job_hunt.llm import chat
from job_hunt.llm.prompts import FOLLOW_UP, NEGOTIATION, THANK_YOU, Prompt

_KIND_PROMPT: dict[str, Prompt] = {
    "thank_you": THANK_YOU,
    "follow_up": FOLLOW_UP,
    "negotiation": NEGOTIATION,
}


def generate_message(
    kind: str,
    *,
    jd_text: str,
    resume_json: dict[str, Any],
    company: str = "",
    role: str = "",
    user_context: str = "",
    thread_summary: str = "",
) -> str:
    """Return a drafted message body of the given kind for a job."""
    prompt_def = _KIND_PROMPT[kind]
    parts: list[str] = []
    if user_context:
        parts.append(user_context)
    parts.append(
        f"Write a {kind.replace('_', '-')} message for "
        f"{role or 'this role'} at {company or 'this company'}.\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{jd_text[:4000]}\n\n"
        "=== CANDIDATE RESUME (structured JSON) ===\n"
        f"{json.dumps(resume_json, ensure_ascii=False)[:3000]}"
    )
    if thread_summary:
        parts.append(f"\n\n=== PRIOR THREAD CONTEXT (structured) ===\n{thread_summary}")
    parts.append("\n\nOutput only the message body.")
    prompt = "".join(parts)
    return chat(
        prompt,
        task="drafting",
        system=prompt_def.system,
        temperature=0.5,
        prompt_name=prompt_def.name,
        prompt_version=prompt_def.version,
    )
