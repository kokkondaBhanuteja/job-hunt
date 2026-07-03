"""Semantic services — embed jobs and find nearest matches (Postgres/pgvector only)."""
from __future__ import annotations

from typing import Any

from job_hunt.embed import embed_text
from job_hunt.storage import repo

_PG_ONLY = "semantic search requires Postgres (set DB_BACKEND=postgres)"


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
