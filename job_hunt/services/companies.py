"""Company services — a research cache + memory ('have I engaged this company before?').

External research fetch (size/funding/tech from the web) is deferred (needs a scraper);
`upsert_company` lets the cache be populated manually or by a future enricher. `history`
is derived from jobs/applications, so it works today.
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.storage import repo


def upsert_company(
    *, name: str, size: str | None = None, funding_stage: str | None = None,
    tech: list[str] | None = None, glassdoor: str | None = None, notes: str | None = None,
) -> int:
    repo.init_db()
    return repo.save_company(
        name=name, size=size, funding_stage=funding_stage,
        tech=tech, glassdoor=glassdoor, notes=notes,
    )


def get_company(name: str) -> dict[str, Any] | None:
    repo.init_db()
    row = repo.get_company(name)
    if row is None:
        return None
    company = dict(row)
    if company.get("tech"):
        company["tech"] = json.loads(company["tech"])
    return company


def company_history(company: str) -> dict[str, Any]:
    """Roles seen + applications made at a company (dedup/context signal)."""
    repo.init_db()
    roles = [dict(r) for r in repo.company_history(company)]
    applied = sum(1 for r in roles if r["applied_at"])
    return {
        "company": company,
        "cached": get_company(company),
        "roles_seen": len(roles),
        "applications": applied,
        "roles": roles,
    }
