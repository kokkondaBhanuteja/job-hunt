"""Interview-prep brief service — generate a structured prep brief for a job.

Combines the job description, company history, and user context into a single
prompt and returns a structured JSON brief from the LLM.
"""
from __future__ import annotations

from typing import Any

from job_hunt.llm.client import chat_json
from job_hunt.llm.prompts import ROLE_BRIEF
from job_hunt.logging_config import get_logger
from job_hunt.services.companies import company_history
from job_hunt.services.context import context_preamble
from job_hunt.storage import repo

logger = get_logger(__name__)


def brief_for_job(job_id: int) -> dict[str, Any]:
    """Return a structured interview-prep brief for the given job, or {error} if not found."""
    repo.init_db()
    job = repo.get_job(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    jd_text = job["description_full"] or job["description"] or ""
    company = job["company"]
    history = company_history(company)
    user_ctx = context_preamble()

    history_lines = (
        f"Roles seen at {company}: {history['roles_seen']}. "
        f"Applications made: {history['applications']}."
    )
    if history["roles"]:
        titles = ", ".join(r["title"] for r in history["roles"][:5])
        history_lines += f" Prior roles: {titles}."

    prompt = (
        f"{user_ctx}"
        f"## Role: {job['title']} at {company}\n\n"
        f"### Job Description\n{jd_text}\n\n"
        f"### Company History\n{history_lines}\n"
    )

    logger.debug("building role brief for job_id=%d company=%r", job_id, company)
    return chat_json(
        prompt,
        schema=ROLE_BRIEF.schema,
        task="drafting",
        system=ROLE_BRIEF.system,
        prompt_name=ROLE_BRIEF.name,
        prompt_version=ROLE_BRIEF.version,
    )
