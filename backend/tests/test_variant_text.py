"""Tests for per-company text-authored résumé variants."""
from __future__ import annotations

import json
import sqlite3

from job_hunt import services
from job_hunt.resume import parser as resume_parser
from job_hunt.storage import repo

_CANNED_PARSED: dict = {
    "slug": "acme-be",
    "headline": "Backend Engineer",
    "tags": ["python", "fastapi"],
    "sections": [],
}

_BODY = r"\section{Experience} Backend Engineer at Acme Corp."


def test_save_variant_from_text_stores_body_company_parsed(tmp_db, monkeypatch):
    """save_variant_from_text stores body, company, and parsed_json; source_path is NULL."""
    monkeypatch.setattr(resume_parser, "chat_json", lambda *a, **kw: _CANNED_PARSED)

    result = services.save_variant_from_text(
        "acme-be", company="Acme", body=_BODY, tags=["python"]
    )
    assert result["slug"] == "acme-be"
    assert result["company"] == "Acme"
    assert "id" in result

    # Verify DB row
    row = repo.get_resume_variant_by_slug("acme-be")
    assert row is not None
    assert row["body"] == _BODY
    assert row["company"] == "Acme"
    assert row["source_path"] is None
    parsed = json.loads(row["parsed_json"])
    assert parsed["headline"] == "Backend Engineer"


def test_get_variant_round_trips(tmp_db, monkeypatch):
    """get_variant returns slug, company, body, parsed_json, tags."""
    monkeypatch.setattr(resume_parser, "chat_json", lambda *a, **kw: _CANNED_PARSED)

    services.save_variant_from_text("acme-be", company="Acme", body=_BODY)
    detail = services.get_variant("acme-be")

    assert detail["slug"] == "acme-be"
    assert detail["company"] == "Acme"
    assert detail["body"] == _BODY
    assert isinstance(detail["parsed_json"], dict)
    assert detail["parsed_json"]["headline"] == "Backend Engineer"


def test_save_variant_empty_body_returns_error(tmp_db):
    """Empty body returns {"error": ...} without touching the DB."""
    result = services.save_variant_from_text("x", company="Y", body="   ")
    assert "error" in result


def test_best_scored_variant_for_company_picks_company_variant(tmp_db, monkeypatch):
    """best_scored_variant_for_company returns the Acme variant over a generic one."""
    monkeypatch.setattr(resume_parser, "chat_json", lambda *a, **kw: _CANNED_PARSED)

    # Seed two variants
    services.save_variant_from_text("acme-be", company="Acme", body=_BODY)
    tmp_db.upsert_resume_variant(
        slug="generic", source_path="/generic.tex",
        parsed={"headline": "Generic"}, tags=[],
    )

    jid = tmp_db.insert_job_if_new(
        dedup_hash="d1", source="naukri", source_job_id=None,
        title="Backend Eng", company="Acme", location=None,
        description="desc", apply_url="https://x/1", posted_date=None,
    )
    acme_id = repo.get_resume_variant_by_slug("acme-be")["id"]
    generic_id = repo.get_resume_variant_by_slug("generic")["id"]

    # Score both — generic higher globally
    tmp_db.write_score(job_id=jid, variant_id=acme_id, fit_score=70, reasoning="ok")
    tmp_db.write_score(job_id=jid, variant_id=generic_id, fit_score=90, reasoning="great")

    company_variant = repo.best_scored_variant_for_company(jid, "Acme")
    assert company_variant is not None
    assert company_variant["slug"] == "acme-be"

    # Fallback: no company match → no company variant (global best still available)
    no_match = repo.best_scored_variant_for_company(jid, "Unknown Corp")
    assert no_match is None
    global_best = repo.best_scored_variant(jid)
    assert global_best["slug"] == "generic"


def test_tailor_for_job_uses_company_variant(tmp_db, monkeypatch):
    """tailor_for_job prefers the company-matched variant even if generic scored higher."""
    from job_hunt.resume import tailor

    monkeypatch.setattr(resume_parser, "chat_json", lambda *a, **kw: _CANNED_PARSED)
    monkeypatch.setattr(tailor, "chat", lambda *a, **k: "# Tailored for Acme")

    services.save_variant_from_text("acme-be", company="Acme", body=_BODY)
    tmp_db.upsert_resume_variant(
        slug="generic", source_path="/generic.tex",
        parsed={"headline": "Generic"}, tags=[],
    )

    jid = tmp_db.insert_job_if_new(
        dedup_hash="d2", source="naukri", source_job_id=None,
        title="Backend", company="Acme", location=None,
        description="NestJS", apply_url="https://x/2", posted_date=None,
    )
    acme_id = repo.get_resume_variant_by_slug("acme-be")["id"]
    generic_id = repo.get_resume_variant_by_slug("generic")["id"]

    # Generic scores higher globally, but Acme variant is company-matched
    tmp_db.write_score(job_id=jid, variant_id=acme_id, fit_score=70, reasoning="ok")
    tmp_db.write_score(job_id=jid, variant_id=generic_id, fit_score=90, reasoning="great")

    result = services.tailor_for_job(jid)
    # Company variant wins despite lower global score
    assert result["variant"] == "acme-be"
    assert result["content"] == "# Tailored for Acme"


def test_list_variants_includes_has_body(tmp_db, monkeypatch):
    """list_variants returns has_body=True for text variant, False for file variant."""
    monkeypatch.setattr(resume_parser, "chat_json", lambda *a, **kw: _CANNED_PARSED)

    services.save_variant_from_text("acme-be", company="Acme", body=_BODY)
    tmp_db.upsert_resume_variant(
        slug="generic", source_path="/generic.tex",
        parsed={"headline": "Generic"}, tags=[],
    )

    variants = services.list_variants()
    slugs = {v["slug"]: v for v in variants}
    assert slugs["acme-be"]["has_body"] is True
    assert slugs["acme-be"]["company"] == "Acme"
    assert slugs["generic"]["has_body"] is False


def test_migration_makes_source_path_nullable(tmp_path, monkeypatch):
    """C1 regression: pre-0024 DB (source_path NOT NULL) is rebuilt by init_db().

    Simulates an existing install: creates the old schema, runs init_db() to apply
    the SQLite migration, then asserts that upsert_variant_from_text (which writes
    source_path=NULL) succeeds and that the existing file-backed row survives intact.
    """
    from job_hunt.storage import db

    path = tmp_path / "old.db"
    monkeypatch.setattr(db, "DB_PATH", path)

    # Simulate a pre-0024 DB: source_path NOT NULL, no company/body columns.
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE resume_variants (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                slug        TEXT UNIQUE NOT NULL,
                source_path TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                tags        TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO resume_variants (slug, source_path, parsed_json, tags, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("file-variant", "/some/file.tex", '{"headline":"Old"}', '["python"]',
             "2024-01-01T00:00:00"),
        )

    # Run migration — must make source_path nullable without losing the existing row.
    db.init_db(path)

    # Text-variant save must now succeed (would raise IntegrityError on un-migrated DB).
    monkeypatch.setattr(resume_parser, "chat_json", lambda *a, **kw: _CANNED_PARSED)
    result = services.save_variant_from_text("acme-be", company="Acme", body=_BODY)
    assert "error" not in result, f"Expected success, got: {result}"
    assert result["slug"] == "acme-be"

    # Existing file-backed row must still be present and correct.
    row = db.get_resume_variant_by_slug("file-variant")
    assert row is not None
    assert row["source_path"] == "/some/file.tex"
    assert row["slug"] == "file-variant"
