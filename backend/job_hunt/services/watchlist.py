"""Company-watchlist service — CRUD over the ATS board watchlist."""
from __future__ import annotations

from typing import Any

from job_hunt.enums import ATSPlatform
from job_hunt.logging_config import get_logger
from job_hunt.storage import repo

logger = get_logger(__name__)


def add_company(company: str, ats: str, board_token: str) -> dict[str, Any]:
    """Insert a watchlist entry; return {id, company, ats, board_token} or {error}."""
    try:
        platform = ATSPlatform(ats)
    except ValueError:
        return {"error": f"unknown ATS '{ats}' — choose from: {', '.join(a.value for a in ATSPlatform)}"}
    repo.init_db()
    watch_id = repo.add_watch(company=company, ats=platform.value, board_token=board_token)
    logger.info("watchlist: added %s (%s token=%s) id=%d", company, ats, board_token, watch_id)
    return {"id": watch_id, "company": company, "ats": platform.value, "board_token": board_token}


def list_watch() -> list[dict[str, Any]]:
    """Return all watchlist entries."""
    repo.init_db()
    return repo.list_watch()


def set_enabled(watch_id: int, enabled: bool) -> dict[str, Any]:
    """Enable or disable a watchlist entry; return {ok: true} or {error}."""
    repo.init_db()
    repo.set_watch_enabled(watch_id, enabled)
    return {"ok": True}


def remove(watch_id: int) -> dict[str, Any]:
    """Delete a watchlist entry by id; return {ok: true}."""
    repo.init_db()
    repo.remove_watch(watch_id)
    return {"ok": True}
