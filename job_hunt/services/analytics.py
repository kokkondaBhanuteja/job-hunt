"""Analytics — turn the platform's data into an optimization dashboard.

Read-only aggregate reporting. The queries are standard, param-free SQL, so they run
verbatim on both backends via `repo.raw_select`.
"""
from __future__ import annotations

from typing import Any

from job_hunt.storage import repo


def variant_performance() -> list[dict[str, Any]]:
    """Per resume variant: applications, interviews (interview/hr/offer), offers, rejections.

    This is 'which resume wins' — the signal the learning loop uses to prefer variants.
    """
    return repo.raw_select(
        "SELECT rv.slug AS variant, COUNT(*) AS applications, "
        "SUM(CASE WHEN a.stage IN ('interview','hr','offer') THEN 1 ELSE 0 END) AS interviews, "
        "SUM(CASE WHEN a.stage = 'offer' THEN 1 ELSE 0 END) AS offers, "
        "SUM(CASE WHEN a.stage = 'rejected' THEN 1 ELSE 0 END) AS rejections "
        "FROM applications a JOIN resume_variants rv ON rv.id = a.variant_id "
        "GROUP BY rv.slug ORDER BY interviews DESC, applications DESC"
    )


def dashboard() -> dict[str, Any]:
    """Funnel, pipeline, LLM cost, source-effectiveness, and variant-performance metrics."""
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
        "variant_performance": variant_performance(),
        "llm_cost": cost[0] if cost else {"calls": 0, "cost": 0, "tokens": 0},
    }
