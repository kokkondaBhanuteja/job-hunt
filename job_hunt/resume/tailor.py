"""Resume tailoring — emphasize the parts of a resume that matter for one JD.

Prose generation through the AI Gateway (`tailoring` task, routable to a stronger model).
Invents nothing — the prompt constrains it to the candidate's real facts.
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.llm.ollama import chat
from job_hunt.llm.prompts import RESUME_TAILOR


def tailor_resume(*, jd_text: str, resume_json: dict[str, Any]) -> str:
    """Return a JD-tailored resume in Markdown."""
    prompt = (
        "Tailor this resume for the job below.\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{jd_text[:5000]}\n\n"
        "=== CANDIDATE RESUME (structured JSON) ===\n"
        f"{json.dumps(resume_json, ensure_ascii=False)[:5000]}\n\n"
        "Output the tailored resume in Markdown."
    )
    return chat(prompt, task="tailoring", system=RESUME_TAILOR.system, temperature=0.3)
