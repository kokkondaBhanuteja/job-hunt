"""APScheduler wiring — the long-running worker process.

Two periodic jobs:
  - discovery+scoring across active profiles (gated to active hours)
  - draining the event outbox

Started via `hunt worker`. Kept thin: all real logic is in `runner` / `pacing`.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from job_hunt.browser.manager import TIMEZONE
from job_hunt.worker import config, pacing, runner

_TZ = ZoneInfo(TIMEZONE)


def _discovery_if_active() -> None:
    now = datetime.now(_TZ)
    if pacing.within_active_hours(
        now.hour, now.minute, start=config.ACTIVE_START, end=config.ACTIVE_END
    ):
        runner.run_all_active_profiles(headless=True)


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler(timezone=_TZ)
    sched.add_job(
        _discovery_if_active, "interval",
        minutes=config.DISCOVERY_INTERVAL_MIN, id="discovery", max_instances=1,
    )
    sched.add_job(
        runner.dispatch_events_once, "interval",
        seconds=config.DISPATCH_INTERVAL_SEC, id="dispatch", max_instances=1,
    )
    # Evening daily report (no-op unless NOTIFY_CHANNEL is configured).
    from job_hunt.services.analytics import send_daily_report

    sched.add_job(send_daily_report, "cron", hour=20, minute=0, id="daily_report")
    return sched


def run() -> None:
    print(
        f"worker: discovery every {config.DISCOVERY_INTERVAL_MIN}min "
        f"(active {config.ACTIVE_START}–{config.ACTIVE_END} {TIMEZONE}, cap {config.DAILY_CAP}/day), "
        f"event dispatch every {config.DISPATCH_INTERVAL_SEC}s. Ctrl-C to stop."
    )
    build_scheduler().start()
