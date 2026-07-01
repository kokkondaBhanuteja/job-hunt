"""Characterization tests for the SQLite repository layer (job_hunt/storage/db.py)."""
from __future__ import annotations


def _insert_job(db, *, company="Acme", title="Backend Engineer", h="hash-1", status_new=True):
    return db.insert_job_if_new(
        dedup_hash=h,
        source="naukri",
        source_job_id=None,
        title=title,
        company=company,
        location="bangalore",
        description="Build APIs in NestJS.",
        apply_url="https://example.com/job/1",
        posted_date="2026-06-29",
    )


def test_insert_job_returns_id_then_dedups(tmp_db):
    first = _insert_job(tmp_db, h="dup-hash")
    assert isinstance(first, int) and first > 0

    # Same dedup_hash → insert is skipped, returns None.
    second = _insert_job(tmp_db, h="dup-hash", title="Senior Backend Engineer")
    assert second is None


def test_upsert_resume_variant_is_idempotent(tmp_db):
    vid1 = tmp_db.upsert_resume_variant(
        slug="backend-node",
        source_path="/x/backend-node.tex",
        parsed={"headline": "Backend Engineer", "skills": {"backend": ["nestjs"]}},
        tags=["nestjs", "aws"],
    )
    vid2 = tmp_db.upsert_resume_variant(
        slug="backend-node",
        source_path="/x/backend-node.tex",
        parsed={"headline": "Backend Engineer v2"},
        tags=["nestjs"],
    )
    assert vid1 == vid2  # same slug → updated in place, not duplicated

    variants = tmp_db.list_resume_variants()
    assert len(variants) == 1
    assert variants[0]["slug"] == "backend-node"


def test_write_score_and_top_matches(tmp_db):
    job_id = _insert_job(tmp_db, h="score-hash")
    vid = tmp_db.upsert_resume_variant(
        slug="backend-node", source_path="/x.tex", parsed={"headline": "x"}, tags=[]
    )
    tmp_db.write_score(job_id=job_id, variant_id=vid, fit_score=88, reasoning="strong overlap")

    # Above threshold → returned with winning variant.
    rows = tmp_db.top_matches(min_score=70, limit=10)
    assert len(rows) == 1
    assert rows[0]["best_score"] == 88
    assert rows[0]["best_variant"] == "backend-node"

    # Below threshold → filtered out.
    assert tmp_db.top_matches(min_score=90, limit=10) == []


def test_list_jobs_for_scoring_excludes_already_scored(tmp_db):
    job_id = _insert_job(tmp_db, h="pending-hash")
    assert [r["id"] for r in tmp_db.list_jobs_for_scoring()] == [job_id]

    vid = tmp_db.upsert_resume_variant(
        slug="v", source_path="/x.tex", parsed={"h": 1}, tags=[]
    )
    tmp_db.write_score(job_id=job_id, variant_id=vid, fit_score=50, reasoning="ok")

    # Once scored, it drops out of the scoring queue.
    assert tmp_db.list_jobs_for_scoring() == []
