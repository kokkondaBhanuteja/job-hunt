"""Postgres backend smoke test — skipped unless a Postgres is reachable.

Read-only (no writes / no pollution of the dev DB): verifies the backend connects,
the schema/migrations are applied, and the repo's read path works. The full
read/write round-trip is exercised manually + by the SQLite contract tests.
"""
from __future__ import annotations

import pytest

from job_hunt.storage import pg


def _pg_available() -> bool:
    try:
        with pg.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="Postgres not reachable")


def test_pg_schema_and_migrations_present():
    pg.init_db()
    tables = {
        r["tablename"]
        for r in pg.raw_select(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
    }
    assert {"jobs", "scores", "resume_variants", "llm_calls"}.issubset(tables)

    applied = {r["filename"] for r in pg.raw_select("SELECT filename FROM schema_migrations")}
    assert "0001_init.sql" in applied


def test_pg_read_path_returns_text_json():
    # list_resume_variants must return parsed_json as TEXT (SQLite parity), if any exist.
    rows = pg.list_resume_variants()
    for r in rows:
        assert isinstance(r["parsed_json"], str)
