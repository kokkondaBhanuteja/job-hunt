"""Company services — history/memory ('have I engaged this company before?').

`history` is derived from jobs/applications. `get_company` returns any cached
company row (kept for the read path; the write path is currently unused).
"""
from __future__ import annotations

import json
from typing import Any

from job_hunt.storage import repo


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
