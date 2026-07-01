"""Review services — read-side queries for the dashboard / MCP host / API."""
from __future__ import annotations

import json
from typing import Any

from job_hunt.enums import Score
from job_hunt.storage import repo as db


def list_top_matches(
    min_score: int = Score.DEFAULT_MIN_MATCH, limit: int = 10
) -> list[dict[str, Any]]:
    """Best-scoring jobs awaiting review, with their winning variant."""
    db.init_db()
    return [dict(row) for row in db.top_matches(min_score=min_score, limit=limit)]


def list_board(limit: int = 200) -> list[dict[str, Any]]:
    """All jobs with their state + best score — grouped by state in the UI (Kanban)."""
    db.init_db()
    return [dict(row) for row in db.list_board_jobs(limit=limit)]


def get_job(job_id: int) -> dict[str, Any]:
    """Full record for one job: JD + all variant scores + reasoning."""
    db.init_db()
    job = db.get_job(job_id)
    if job is None:
        return {"error": f"No job with id={job_id}"}
    scores = db.list_scores_for_job(job_id)
    return {"job": dict(job), "scores": [dict(s) for s in scores]}


def list_resume_vault() -> list[dict[str, Any]]:
    """List resume variants and their tags."""
    db.init_db()
    return [
        {
            "id": int(r["id"]),
            "slug": r["slug"],
            "tags": json.loads(r["tags"]),
            "source_path": r["source_path"],
            "updated_at": r["updated_at"],
        }
        for r in db.list_resume_variants()
    ]
