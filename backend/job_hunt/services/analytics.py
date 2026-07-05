"""Analytics — turn the platform's data into an optimization dashboard.

Read-only aggregate reporting. The queries are standard, param-free SQL, so they run
verbatim on both backends via `repo.raw_select`.
"""
from __future__ import annotations

from datetime import datetime
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


def funnel_metrics() -> dict[str, Any]:
    """Return interview/offer rates, stage conversion, time-to-interview, and source effectiveness.

    All SQL is param-free (no ? / %s) so the same queries run on SQLite and Postgres.
    Division-by-zero guards return 0.0 when the denominator is zero.
    """
    repo.init_db()

    def _rate(num: int, den: int) -> float:
        return round(num / den, 3) if den else 0.0

    # --- aggregate counts from applications ---
    totals = repo.raw_select(
        "SELECT "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN stage IN ('interview','hr','offer') THEN 1 ELSE 0 END) AS interviews, "
        "SUM(CASE WHEN stage = 'offer' THEN 1 ELSE 0 END) AS offers, "
        "SUM(CASE WHEN stage = 'rejected' THEN 1 ELSE 0 END) AS rejections, "
        "SUM(CASE WHEN reply_type IS NOT NULL THEN 1 ELSE 0 END) AS with_reply "
        "FROM applications"
    )
    row = totals[0] if totals else {}
    total: int = int(row.get("total") or 0)
    interviews: int = int(row.get("interviews") or 0)
    offers: int = int(row.get("offers") or 0)
    rejections: int = int(row.get("rejections") or 0)
    with_reply: int = int(row.get("with_reply") or 0)

    interview_rate = _rate(interviews, total)
    offer_rate = _rate(offers, total)
    response_rate = _rate(with_reply, total)
    stage_conversion = {
        "applied_to_interview": interview_rate,
        "interview_to_offer": _rate(offers, interviews),
    }

    # --- median time from applied→interview (days) via job_transitions ---
    tti_rows = repo.raw_select(
        "SELECT job_id, "
        "MIN(CASE WHEN to_state='applied' THEN created_at END) AS applied_at, "
        "MIN(CASE WHEN to_state='interview' THEN created_at END) AS interview_at "
        "FROM job_transitions GROUP BY job_id"
    )
    deltas: list[float] = []
    for r in tti_rows:
        a_ts = r.get("applied_at")
        i_ts = r.get("interview_at")
        if a_ts and i_ts:
            try:
                a_dt = datetime.fromisoformat(str(a_ts))
                i_dt = datetime.fromisoformat(str(i_ts))
                deltas.append((i_dt - a_dt).total_seconds() / 86400.0)
            except ValueError:
                pass

    time_to_interview_days: float | None = None
    if deltas:
        deltas.sort()
        mid = len(deltas) // 2
        if len(deltas) % 2:
            time_to_interview_days = round(deltas[mid], 1)
        else:
            time_to_interview_days = round((deltas[mid - 1] + deltas[mid]) / 2, 1)

    # --- per-source: applied / interview / offer counts + interview_rate ---
    src_rows = repo.raw_select(
        "SELECT j.source AS source, "
        "COUNT(*) AS applied, "
        "SUM(CASE WHEN a.stage IN ('interview','hr','offer') THEN 1 ELSE 0 END) AS interviews, "
        "SUM(CASE WHEN a.stage = 'offer' THEN 1 ELSE 0 END) AS offers "
        "FROM applications a JOIN jobs j ON j.id = a.job_id "
        "GROUP BY j.source ORDER BY applied DESC"
    )
    source_effectiveness_by_outcome = [
        {
            "source": r["source"],
            "applied": int(r["applied"]),
            "interviews": int(r["interviews"]),
            "offers": int(r["offers"]),
            "interview_rate": _rate(int(r["interviews"]), int(r["applied"])),
        }
        for r in src_rows
    ]

    return {
        "applications_total": total,
        "interviews": interviews,
        "offers": offers,
        "rejections": rejections,
        "interview_rate": interview_rate,
        "offer_rate": offer_rate,
        "response_rate": response_rate,
        "stage_conversion": stage_conversion,
        "time_to_interview_days": time_to_interview_days,
        "source_effectiveness_by_outcome": source_effectiveness_by_outcome,
    }


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
        "funnel_metrics": funnel_metrics(),
    }


def daily_report_text() -> str:
    """Compose the daily report from the dashboard (services own cross-module wiring)."""
    from job_hunt.notify.report import build_daily_report

    return build_daily_report(dashboard())


def send_daily_report(notifier: Any = None) -> bool:
    from job_hunt.notify.report import send_report

    return send_report(daily_report_text(), notifier)


def send_test_notification() -> dict[str, Any]:
    """Send a one-off test message via the configured channel. Returns {channel, sent}."""
    from job_hunt.notify.base import get_notifier

    notifier = get_notifier()
    sent = notifier.send("✅ Job-hunt notifications are wired — updates will land here.")
    return {"channel": notifier.name, "sent": sent}
