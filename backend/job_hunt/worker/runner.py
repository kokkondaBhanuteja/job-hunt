"""Worker run logic — one discovery+scoring cycle per profile, wrapped in a run.

Each cycle creates a first-class `runs` row (running → done/failed/cancelled), logs
progress, checks the cooperative cancel flag, and scores afterwards. The scheduler
just calls these on a cadence; the actual crawl lives behind the Source plugin.
"""
from __future__ import annotations

from typing import Any

from job_hunt.enums import EventType, RunStatus, ScrapeStatus
from job_hunt.events import bus
from job_hunt.logging_config import get_logger
from job_hunt.plugins import get_source
from job_hunt.scoring.match import score_all_pending
from job_hunt.services.discovery import discover
from job_hunt.storage import repo
from job_hunt.worker import config, pacing

logger = get_logger(__name__)


def run_discovery_cycle(
    profile: dict[str, Any],
    *,
    source_name: str = "naukri",
    headless: bool = True,
    score: bool = True,
) -> dict[str, Any]:
    """Run one source discovery for `profile`, then score. Returns a summary dict."""
    src = get_source(source_name)
    run_id = repo.create_run([source_name])
    repo.start_run(run_id)
    repo.append_run_log(
        run_id, f"discover {profile['keywords']!r} @ {profile['location']!r} via {source_name}"
    )
    try:
        result = src.discover(
            keyword=profile["keywords"],
            location=profile["location"],
            pages=int(profile.get("pages", 1) or 1),
            headless=headless,
        )
        health = result.get("health")
        repo.append_run_log(
            run_id, f"found={result['found']} new={result['new']} health={health or 'ok'}"
        )

        # login wall / captcha — fail loudly, don't let it look "empty"
        if health == ScrapeStatus.BLOCKED:
            bus.emit(EventType.SCRAPE_BLOCKED, payload={"source": source_name})
            repo.finish_run(run_id, RunStatus.FAILED, jobs_found=result["found"],
                            jobs_new=result["new"], errors={"scrape": "blocked"})
            return {"run_id": run_id, "status": RunStatus.FAILED, **result}

        if repo.run_cancel_requested(run_id):
            repo.finish_run(run_id, RunStatus.CANCELLED,
                            jobs_found=result["found"], jobs_new=result["new"])
            return {"run_id": run_id, "status": RunStatus.CANCELLED, **result}

        if score:
            try:
                summary = score_all_pending()
                repo.append_run_log(run_id, f"scored {summary}")
            except RuntimeError as exc:  # no resume variants yet
                repo.append_run_log(run_id, f"scoring skipped: {exc}")

        repo.finish_run(run_id, RunStatus.DONE,
                        jobs_found=result["found"], jobs_new=result["new"])
        return {"run_id": run_id, "status": RunStatus.DONE, **result}

    except Exception as exc:  # noqa: BLE001 — record failure on the run, don't crash the worker
        repo.append_run_log(run_id, f"ERROR: {exc}")
        repo.finish_run(run_id, RunStatus.FAILED, errors={"message": str(exc)})
        return {"run_id": run_id, "status": RunStatus.FAILED, "error": str(exc)}


def run_all_active_profiles(*, headless: bool = True) -> list[dict[str, Any]]:
    """Run a discovery cycle for every enabled search profile, up to the daily cap."""
    repo.init_db()
    if pacing.cap_reached(repo.count_runs_today(), config.DAILY_CAP):
        logger.info(
            "daily discovery cap (%d runs) reached — skipping this cycle",
            config.DAILY_CAP,
        )
        return []
    return [run_discovery_cycle(p, headless=headless) for p in repo.list_active_search_profiles()]


def run_api_sources() -> None:
    """Poll all registered API sources for every active search profile.

    Iterates each active profile × each source in config.API_SOURCES, calling
    discover() for each pair. Unregistered or failing sources are skipped
    gracefully — a warning is logged and the loop continues. No browser
    daily-cap gate (these are cheap httpx sources). Safe to run repeatedly.
    """
    repo.init_db()
    profiles = repo.list_active_search_profiles()
    total_found = 0
    total_new = 0
    for profile in profiles:
        for src in config.API_SOURCES:
            try:
                result = discover(src, keyword=profile["keywords"], location=profile["location"])
                total_found += result.get("found", 0)
                total_new += result.get("new", 0)
            except Exception:  # noqa: BLE001 — skip absent/failing sources
                logger.warning(
                    "api source %s failed/absent for profile %s — skipping",
                    src,
                    profile.get("name"),
                    exc_info=True,
                )
                continue
    logger.info(
        "api_sources cycle complete: %d profile(s), %d found, %d new",
        len(profiles),
        total_found,
        total_new,
    )
    run_watchlist()


def run_watchlist() -> None:
    """Poll ATS boards for every enabled watchlist entry.

    Calls discover() for each active watch row. Unregistered or failing sources
    are logged and skipped — the loop always continues.
    """
    repo.init_db()
    watches = repo.list_active_watch()
    for watch in watches:
        try:
            discover(watch["ats"], keyword=watch["board_token"], location="")
        except Exception:  # noqa: BLE001
            logger.warning(
                "watchlist discover failed for %s (%s token=%s) — skipping",
                watch.get("company"),
                watch.get("ats"),
                watch.get("board_token"),
                exc_info=True,
            )


def dispatch_events_once(handlers: dict[str, Any] | None = None) -> int:
    """Drain the event outbox once (the worker calls this on a short cadence).

    Defaults to the real pipeline handlers (discovered→enrich, enriched→score).
    """
    if handlers is None:
        from job_hunt.worker.handlers import default_handlers

        handlers = default_handlers()
    return bus.dispatch_pending(handlers)
