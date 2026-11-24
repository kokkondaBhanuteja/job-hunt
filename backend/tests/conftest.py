"""Shared fixtures for the characterization test net.

These tests pin the *current* v0 behavior before the Phase 0 refactor so we can
refactor (LLM registry, services layer, directory move) without silent drift.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _location_filter_off(monkeypatch):
    """Plugin tests use real-world (often US) sample locations; they test parsing, not policy.

    tests/test_location.py switches the India/remote filter back on for its own cases.
    """
    from job_hunt.sources import location

    monkeypatch.setattr(location, "JOB_LOCATION_FILTER", "off")


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect storage to a throwaway SQLite file.

    `db.connect()` / `db.init_db()` resolve `DB_PATH` at call time, so
    monkeypatching the module global redirects every repository function.
    """
    from job_hunt.storage import db

    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db(path)
    return db
