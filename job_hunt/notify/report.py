"""Daily report — compact status summary. Pure formatting given a metrics dict
(the analytics-dashboard shape); a service supplies the metrics. No `services/` import."""
from __future__ import annotations

from typing import Any

from job_hunt.notify.base import Notifier, get_notifier


def build_daily_report(metrics: dict[str, Any]) -> str:
    """Compose the daily summary from an analytics-dashboard dict."""
    by_state = {row["state"]: row["n"] for row in metrics["jobs_by_state"]}
    funnel = {row["stage"]: row["n"] for row in metrics["funnel"]}
    total = sum(by_state.values())

    lines = ["📋 Job-Hunt daily report", f"Jobs tracked: {total}"]
    if by_state:
        lines.append("  " + "  ".join(f"{state}={n}" for state, n in by_state.items()))
    lines.append(
        f"Applied: {funnel.get('applied', 0)}  ·  OA: {funnel.get('oa', 0)}  ·  "
        f"Interview: {funnel.get('interview', 0)}  ·  Offer: {funnel.get('offer', 0)}"
    )
    cost = metrics["llm_cost"]
    lines.append(f"LLM spend: ${float(cost['cost']):.4f} over {cost['calls']} calls")
    return "\n".join(lines)


def send_report(text: str, notifier: Notifier | None = None) -> bool:
    """Send a prepared report to the configured channel. Returns True if delivered."""
    return (notifier or get_notifier()).send(text)
