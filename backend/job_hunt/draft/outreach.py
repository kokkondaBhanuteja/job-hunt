"""Recruiter-outreach messages — LLM generation, plus deterministic cold-email checks.

`check_email_text` and `build_follow_up_body` involve no LLM: the cold email itself is
written in Claude Code (ai-job-search) and only stored/sent here, so the tone rules are
enforced with plain, testable checks.
"""
from __future__ import annotations

import json
import re
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


# ---------- cold-email checks (deterministic, no LLM) ----------

MAX_BODY_WORDS = 150   # body incl. signature; the target is 80–120
MAX_SUBJECT_WORDS = 8

# Clichés and inflated claims that make a cold email read as generic or exaggerated.
_BANNED_PHRASES = (
    "i hope this email finds you well",
    "i am writing to",
    "passionate",
    "rockstar",
    "ninja",
    "guru",
    "world-class",
    "cutting-edge",
    "synergy",
    "dream company",
)

# [Name], {{company}}, <First Name> — never a markdown link like [text](url).
_PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{1,40}\](?!\()|\{\{[^}\n]*\}\}|<[A-Z][A-Za-z ]{1,30}>")
_MARKDOWN_RE = re.compile(r"\*\*|__|`|\]\(|^#{1,6}\s", re.MULTILINE)


def find_placeholders(text: str) -> list[str]:
    """Return unfilled template placeholders in *text* (these block sending)."""
    return _PLACEHOLDER_RE.findall(text)


def check_email_text(subject: str, body: str) -> list[str]:
    """Return human-readable warnings for a cold email; an empty list means it reads clean."""
    warnings: list[str] = []
    subject_words = len(subject.split())
    if subject_words == 0:
        warnings.append("subject is empty")
    elif subject_words > MAX_SUBJECT_WORDS:
        warnings.append(f"subject is {subject_words} words (keep it to {MAX_SUBJECT_WORDS})")
    body_words = len(body.split())
    if body_words > MAX_BODY_WORDS:
        warnings.append(f"body is {body_words} words (keep it under {MAX_BODY_WORDS})")
    for placeholder in find_placeholders(f"{subject}\n{body}"):
        warnings.append(f"unfilled placeholder: {placeholder}")
    if _MARKDOWN_RE.search(body):
        warnings.append("markdown formatting — send plain text")
    lowered = f"{subject}\n{body}".lower()
    warnings.extend(f"avoid the phrase: {p!r}" for p in _BANNED_PHRASES if p in lowered)
    return warnings


def build_follow_up_body(*, first_name: str, role: str, sender_name: str) -> str:
    """Return the fixed, short follow-up note sent once if the first email gets no reply."""
    about = f" about the {role} role" if role.strip() else ""
    return (
        f"Hi {first_name.strip() or 'there'},\n\n"
        f"Following up on my note below{about}. If someone else on your team is the right "
        "person to ask, a pointer would be much appreciated.\n\n"
        "If now isn't a good time, no need to reply. I won't follow up again.\n\n"
        f"Thanks,\n{sender_name.strip()}"
    )
