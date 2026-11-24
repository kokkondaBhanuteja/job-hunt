"""Postgres connection reuse (storage/pg.connect) — skipped unless a Postgres is reachable.

Uses only a session TEMP table, so nothing is written to the real schema.
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


def _backend_pid(conn) -> int:
    return conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]


def test_sequential_blocks_reuse_one_connection():
    with pg.connect() as a:
        first = _backend_pid(a)
    with pg.connect() as b:
        second = _backend_pid(b)
    assert first == second


def test_each_block_is_still_its_own_transaction():
    with pg.connect() as conn:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS reuse_probe (n int)")
        conn.execute("TRUNCATE reuse_probe")
    with pytest.raises(RuntimeError), pg.connect() as conn:
        conn.execute("INSERT INTO reuse_probe VALUES (1)")
        raise RuntimeError("boom")  # must roll back the insert
    with pg.connect() as conn:
        conn.execute("INSERT INTO reuse_probe VALUES (2)")
    with pg.connect() as conn:
        rows = [r["n"] for r in conn.execute("SELECT n FROM reuse_probe").fetchall()]
    assert rows == [2]


def test_failed_sql_leaves_the_connection_usable():
    with pytest.raises(Exception), pg.connect() as conn:  # noqa: B017 — any DB error
        conn.execute("SELECT * FROM no_such_table_xyz")
    with pg.connect() as conn:
        assert conn.execute("SELECT 1 AS one").fetchone()["one"] == 1


def test_nested_block_gets_its_own_connection():
    with pg.connect() as outer:
        with pg.connect() as inner:
            assert _backend_pid(inner) != _backend_pid(outer)


def test_idle_connection_is_replaced(monkeypatch):
    with pg.connect() as conn:
        before = _backend_pid(conn)
    monkeypatch.setattr(pg, "CONNECTION_MAX_IDLE_S", -1.0)
    with pg.connect() as conn:
        assert _backend_pid(conn) != before


def test_closed_connection_is_replaced():
    with pg.connect() as conn:
        before = _backend_pid(conn)
    pg._local.conn.close()
    with pg.connect() as conn:
        assert _backend_pid(conn) != before


def test_raw_select_never_makes_the_shared_connection_read_only():
    pg.raw_select("SELECT 1 AS one")
    with pg.connect() as conn:
        assert conn.read_only is not True
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS ro_probe (n int)")  # a write must work
