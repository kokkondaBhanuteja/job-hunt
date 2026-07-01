"""APScheduler wiring — the long-running worker process.

Two periodic jobs:
  - discovery+scoring across active profiles (gated to active hours)
  - draining the event outbox

Started via `hunt worker`. Kept thin: all real logic is in `runner` / `pacing`.
"""
from __future__ import annotations

import signal
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from job_hunt.browser.manager import TIMEZONE
from job_hunt.logging_config import get_logger
from job_hunt.storage import repo
from job_hunt.worker import config, pacing, runner

logger = get_logger(__name__)
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
    # Crash recovery: a previous worker killed mid-crawl leaves runs stuck 'running'.
    reaped = repo.reap_stale_runs()
    if reaped:
        logger.warning("reaped %d stale run(s) left 'running' by a previous worker", reaped)

    logger.info(
        "worker: discovery every %dmin (active %s–%s %s, cap %d/day), "
        "event dispatch every %ds. Ctrl-C to stop.",
        config.DISCOVERY_INTERVAL_MIN, config.ACTIVE_START, config.ACTIVE_END, TIMEZONE,
        config.DAILY_CAP, config.DISPATCH_INTERVAL_SEC,
    )
    sched = build_scheduler()

    def _shutdown(signum: int, _frame: object) -> None:
        logger.info("received signal %d — shutting down worker gracefully", signum)
        sched.shutdown(wait=True)

    signal.signal(signal.SIGTERM, _shutdown)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("worker interrupted — shutting down")
        sched.shutdown(wait=True)
