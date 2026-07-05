"""Tests for similar_successful — outcome-aware embedding similarity.

Runs entirely on SQLite / stub embedder (no live Ollama, no live Postgres).
The Postgres pgvector path is gated behind `_pg_available()` exactly as in
test_semantic.py.
"""
from __future__ import annotations

import pytest

from job_hunt.services import similar_successful
from job_hunt.storage import pg  # noqa: F401 — used in _pg_available and gated tests

# ---------- helpers ----------


def _pg_available() -> bool:
    try:
        with pg.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


# ---------- SQLite / no-embedding path (always runs) ----------


def test_similar_successful_sqlite_returns_error_not_raises(tmp_db):
    """On SQLite backend, similar_successful must return an error dict, never raise."""
    result = similar_successful(job_id=9999, limit=5)
    assert isinstance(result, dict)
    assert "error" in result


def test_similar_successful_error_message_contains_embed_hint(tmp_db):
    """The graceful error points the user to `hunt embed`."""
    result = similar_successful(job_id=1, limit=5)
    assert "error" in result
    assert "embed" in result["error"].lower()


def test_similar_successful_does_not_mutate_state(tmp_db):
    """Calling similar_successful twice on the same job_id yields the same result."""
    r1 = similar_successful(job_id=42, limit=5)
    r2 = similar_successful(job_id=42, limit=5)
    assert r1 == r2


def test_similar_successful_service_filters_states(monkeypatch):
    """Service layer passes only INTERVIEW/HR/OFFER states, and shapes the return dict."""
    from job_hunt.storage import repo

    captured: dict = {}

    def _fake_filtered(job_id: int, states: list[str], limit: int) -> list[dict]:
        captured["job_id"] = job_id
        captured["states"] = states
        captured["limit"] = limit
        return [
            {
                "id": 7,
                "title": "Python Lead",
                "company": "Acme",
                "location": "remote",
                "apply_url": "https://x/7",
                "state": "interview",
                "distance": 0.05,
            }
        ]

    monkeypatch.setattr(repo, "semantic_jobs_filtered", _fake_filtered)
    monkeypatch.setattr(repo, "init_db", lambda: None)

    result = similar_successful(job_id=99, limit=3)

    assert "error" not in result
    assert result["job_id"] == 99
    assert result["count"] == 1
    assert result["matches"][0]["job_id"] == 7
    assert result["matches"][0]["state"] == "interview"
    assert captured["states"] == ["interview", "hr", "offer"]
    assert captured["limit"] == 3
    assert 99 not in {m["job_id"] for m in result["matches"]}


def test_similar_successful_service_no_embedding_graceful(monkeypatch):
    """When semantic_jobs_filtered returns [] (no embedding on query job), return error."""
    from job_hunt.storage import repo

    monkeypatch.setattr(repo, "semantic_jobs_filtered", lambda *a, **kw: [])
    monkeypatch.setattr(repo, "init_db", lambda: None)

    result = similar_successful(job_id=42, limit=5)

    # Empty list → empty matches (not an error)
    assert "error" not in result
    assert result["count"] == 0
    assert result["matches"] == []


# ---------- pgvector path (gated — skipped without live Postgres) ----------


@pytest.mark.skipif(not _pg_available(), reason="Postgres not reachable")
def test_pg_semantic_jobs_filtered_only_successful_states(monkeypatch):
    """pg.semantic_jobs_filtered only returns INTERVIEW/HR/OFFER states."""
    monkeypatch.setenv("EMBED_PROVIDER", "stub")
    from job_hunt.embed import embed_text
    from job_hunt.storage import pg as _pg

    _pg.init_db()

    def _insert(dedup, title, state):
        jid = _pg.insert_job_if_new(
            dedup_hash=dedup, source="test", source_job_id=None,
            title=title, company="SimTest", location="remote",
            description=f"{title} test description.",
            apply_url=f"https://x/{dedup}", posted_date=None,
        )
        if jid is None:
            rows = _pg.raw_select(f"SELECT id FROM jobs WHERE dedup_hash='{dedup}'")
            jid = rows[0]["id"]
        _pg.set_job_embedding(jid, embed_text(f"{title} test description."))
        _pg.set_job_state(jid, state)
        return jid

    query_id = _insert("simtest-query", "Python Backend Engineer", "scored")
    _insert("simtest-interview", "Python Senior Engineer", "interview")
    _insert("simtest-hr", "Python Staff Engineer", "hr")
    _insert("simtest-offer", "Python Principal Engineer", "offer")
    _insert("simtest-rejected", "Python Engineer Rejected", "rejected")
    _insert("simtest-discovered", "Python Discovered Engineer", "discovered")

    rows = _pg.semantic_jobs_filtered(
        query_id, ["interview", "hr", "offer"], limit=10
    )

    states_returned = {r["state"] for r in rows}
    assert states_returned <= {"interview", "hr", "offer"}, (
        f"Expected only interview/hr/offer, got {states_returned}"
    )
    # query job itself must not appear
    returned_ids = {r["id"] for r in rows}
    assert query_id not in returned_ids


@pytest.mark.skipif(not _pg_available(), reason="Postgres not reachable")
def test_pg_semantic_jobs_filtered_no_embedding_returns_empty(monkeypatch):
    """pg.semantic_jobs_filtered returns [] when the query job has no embedding."""
    from job_hunt.storage import pg as _pg

    _pg.init_db()
    jid = _pg.insert_job_if_new(
        dedup_hash="simtest-noembedding", source="test", source_job_id=None,
        title="No Embedding Job", company="SimTest", location="remote",
        description="no embedding here.",
        apply_url="https://x/simtest-noembedding", posted_date=None,
    )
    if jid is None:
        rows = _pg.raw_select("SELECT id FROM jobs WHERE dedup_hash='simtest-noembedding'")
        jid = rows[0]["id"]
    with _pg.connect() as conn:
        conn.execute("UPDATE jobs SET embedding = NULL WHERE id = %s", (jid,))

    result = _pg.semantic_jobs_filtered(jid, ["interview", "hr", "offer"], limit=5)
    assert result == []
