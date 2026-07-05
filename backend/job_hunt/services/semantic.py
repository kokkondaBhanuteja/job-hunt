"""Semantic services — embed jobs and find nearest matches (Postgres/pgvector only)."""
from __future__ import annotations

from typing import Any

from job_hunt.embed import embed_text
from job_hunt.enums import JobState
from job_hunt.storage import repo

_PG_ONLY = "semantic search requires Postgres (set DB_BACKEND=postgres)"
_NO_EMBEDDING = "no embedding for this job — run `hunt embed` (Postgres only)"


def embed_jobs(limit: int = 200) -> dict[str, Any]:
    """Embed jobs that don't have a vector yet (uses full JD if enriched)."""
    if repo.backend != "postgres":
        return {"error": _PG_ONLY}
    repo.init_db()
    candidates = repo.jobs_missing_embedding(limit=limit)
    for job in candidates:
        text = job["description_full"] or job["description"] or f"{job['title']} {job['company']}"
        repo.set_job_embedding(int(job["id"]), embed_text(text))
    return {"candidates": len(candidates), "embedded": len(candidates)}


def semantic_match(query: str, limit: int = 10) -> dict[str, Any]:
    """Find jobs nearest to a free-text query by embedding similarity."""
    if repo.backend != "postgres":
        return {"error": _PG_ONLY, "results": []}
    repo.init_db()
    results = repo.semantic_jobs(embed_text(query), limit=limit)
    return {"query": query, "results": [dict(r) for r in results]}


def similar_successful(job_id: int, limit: int = 5) -> dict[str, Any]:
    """Return jobs similar to job_id that reached interview, HR, or offer stage.

    Finds the nearest neighbours by embedding cosine distance, filtered to states
    INTERVIEW, HR, and OFFER.  Returns a graceful error dict if the job has no
    embedding or the backend is SQLite (Postgres/pgvector only).
    """
    repo.init_db()
    states = [JobState.INTERVIEW.value, JobState.HR.value, JobState.OFFER.value]
    try:
        rows = repo.semantic_jobs_filtered(job_id, states, limit=limit)
    except NotImplementedError:
        return {"error": _NO_EMBEDDING}
    if rows is None:
        return {"error": _NO_EMBEDDING}
    matches = [
        {
            "job_id": int(r["id"]),
            "title": r["title"],
            "company": r["company"],
            "distance": float(r["distance"]),
            "state": r["state"],
        }
        for r in rows
    ]
    return {"job_id": job_id, "matches": matches, "count": len(matches)}
