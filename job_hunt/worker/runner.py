"""Worker run logic — one discovery+scoring cycle per profile, wrapped in a run.

Each cycle creates a first-class `runs` row (running → done/failed/cancelled), logs
progress, checks the cooperative cancel flag, and scores afterwards. The scheduler
just calls these on a cadence; the actual crawl lives behind the Source plugin.
"""
from __future__ import annotations

from typing import Any

from job_hunt.enums import RunStatus
from job_hunt.events import bus
from job_hunt.plugins import get_source
from job_hunt.scoring.match import score_all_pending
from job_hunt.storage import repo


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
        repo.append_run_log(run_id, f"found={result['found']} new={result['new']}")

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
    """Run a discovery cycle for every enabled search profile."""
    repo.init_db()
    return [run_discovery_cycle(p, headless=headless) for p in repo.list_active_search_profiles()]


def dispatch_events_once(handlers: dict[str, Any] | None = None) -> int:
    """Drain the event outbox once (the worker calls this on a short cadence).

    Defaults to the real pipeline handlers (discovered→enrich, enriched→score).
    """
    if handlers is None:
        from job_hunt.worker.handlers import default_handlers

        handlers = default_handlers()
    return bus.dispatch_pending(handlers)
