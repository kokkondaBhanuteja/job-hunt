"""Daily report — a compact status summary sent to the configured channel."""
from __future__ import annotations

from job_hunt.notify.base import Notifier, get_notifier
from job_hunt.services.analytics import dashboard


def build_daily_report() -> str:
    """Compose the daily summary from the analytics dashboard."""
    d = dashboard()
    by_state = {row["state"]: row["n"] for row in d["jobs_by_state"]}
    funnel = {row["stage"]: row["n"] for row in d["funnel"]}
    total = sum(by_state.values())

    lines = [
        "📋 Job-Hunt daily report",
        f"Jobs tracked: {total}",
    ]
    if by_state:
        lines.append("  " + "  ".join(f"{state}={n}" for state, n in by_state.items()))
    lines.append(
        f"Applied: {funnel.get('applied', 0)}  ·  OA: {funnel.get('oa', 0)}  ·  "
        f"Interview: {funnel.get('interview', 0)}  ·  Offer: {funnel.get('offer', 0)}"
    )
    cost = d["llm_cost"]
    lines.append(f"LLM spend: ${float(cost['cost']):.4f} over {cost['calls']} calls")
    return "\n".join(lines)


def send_daily_report(notifier: Notifier | None = None) -> bool:
    """Build + send the daily report. Returns True if it was delivered."""
    return (notifier or get_notifier()).send(build_daily_report())
