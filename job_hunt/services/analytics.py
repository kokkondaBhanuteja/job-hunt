"""Analytics — turn the platform's data into an optimization dashboard.

Read-only aggregate reporting. The queries are standard, param-free SQL, so they run
verbatim on both backends via `repo.raw_select`.
"""
from __future__ import annotations

from typing import Any

from job_hunt.storage import repo


def dashboard() -> dict[str, Any]:
    """Funnel, pipeline, LLM cost, and source-effectiveness metrics."""
    repo.init_db()
    cost = repo.raw_select(
        "SELECT count(*) AS calls, COALESCE(SUM(cost),0) AS cost, "
        "COALESCE(SUM(COALESCE(prompt_tokens,0)+COALESCE(completion_tokens,0)),0) AS tokens "
        "FROM llm_calls"
    )
    return {
        "jobs_by_state": repo.raw_select(
            "SELECT state, count(*) AS n FROM jobs GROUP BY state ORDER BY n DESC"
        ),
        "jobs_by_source": repo.raw_select(
            "SELECT source, count(*) AS n FROM jobs GROUP BY source ORDER BY n DESC"
        ),
        "funnel": repo.raw_select(
            "SELECT stage, count(*) AS n FROM applications GROUP BY stage"
        ),
        "source_effectiveness": repo.raw_select(
            "SELECT j.source AS source, count(*) AS applied "
            "FROM applications a JOIN jobs j ON j.id = a.job_id "
            "GROUP BY j.source ORDER BY applied DESC"
        ),
        "llm_by_task": repo.raw_select(
            "SELECT task, count(*) AS calls, COALESCE(SUM(cost),0) AS cost "
            "FROM llm_calls GROUP BY task ORDER BY calls DESC"
        ),
        "llm_cost": cost[0] if cost else {"calls": 0, "cost": 0, "tokens": 0},
    }
