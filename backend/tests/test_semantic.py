"""Tests for embeddings + semantic search.

The embedder is tested purely (stub). The vector round-trip is Postgres-only and
gated — skipped unless a Postgres is reachable.
"""
from __future__ import annotations

import pytest

from job_hunt.embed import EMBED_DIM, embed_text
from job_hunt.storage import pg

# ---------- embedder (pure) ----------


def test_stub_embed_is_deterministic_unit_vector(monkeypatch):
    monkeypatch.setenv("EMBED_PROVIDER", "stub")
    v1 = embed_text("backend engineer kafka")
    v2 = embed_text("backend engineer kafka")
    v3 = embed_text("frontend designer figma")

    assert len(v1) == EMBED_DIM
    assert v1 == v2                      # deterministic
    assert v1 != v3                      # different text → different vector
    assert abs(sum(x * x for x in v1) ** 0.5 - 1.0) < 1e-6  # unit norm


# ---------- pgvector round-trip (gated) ----------


def _pg_available() -> bool:
    try:
        with pg.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _pg_available(), reason="Postgres not reachable")
def test_semantic_search_finds_nearest(monkeypatch):
    monkeypatch.setenv("EMBED_PROVIDER", "stub")
    pg.init_db()  # applies 0008 (vector ext + embedding columns)

    jid = pg.insert_job_if_new(
        dedup_hash="semtest-kafka", source="test", source_job_id=None,
        title="Kafka Streams Engineer", company="SemTest", location="remote",
        description="Kafka, Spring Boot, event streaming backend.",
        apply_url="https://x/sem", posted_date=None,
    )
    if jid is None:  # re-run: fetch existing
        jid = pg.raw_select("SELECT id FROM jobs WHERE dedup_hash='semtest-kafka'")[0]["id"]

    pg.set_job_embedding(jid, embed_text("Kafka, Spring Boot, event streaming backend."))
    hits = pg.semantic_jobs(embed_text("Kafka, Spring Boot, event streaming backend."), limit=5)
    assert any(h["id"] == jid for h in hits)
    # distance to (near-)identical text should be small.
    mine = next(h for h in hits if h["id"] == jid)
    assert mine["distance"] < 0.05
