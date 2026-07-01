"""Recruiter CRM services — contacts per company (fills the v0 `contacts` table)."""
from __future__ import annotations

from typing import Any

from job_hunt.storage import repo


def add_contact(
    *, company: str, name: str, role: str | None = None, persona: str | None = None,
    email_guess: str | None = None, linkedin_url: str | None = None, notes: str | None = None,
) -> int:
    repo.init_db()
    return repo.save_contact(
        company=company, name=name, role=role, persona=persona,
        email_guess=email_guess, linkedin_url=linkedin_url, notes=notes,
    )


def list_contacts(company: str | None = None) -> list[dict[str, Any]]:
    repo.init_db()
    return [dict(r) for r in repo.list_contacts(company)]
