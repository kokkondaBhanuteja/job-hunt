"""Tests for the company watchlist feature (service + storage + worker integration)."""
from __future__ import annotations

from job_hunt.services import watchlist as svc
from job_hunt.storage import repo
from job_hunt.worker.runner import run_watchlist

# ── storage / service tests ────────────────────────────────────────────────


def test_add_and_list_active(tmp_db):
    result = svc.add_company("Stripe", "greenhouse", "stripe")
    assert result["id"] >= 1
    active = repo.list_active_watch()
    assert len(active) == 1
    assert active[0]["company"] == "Stripe"
    assert active[0]["ats"] == "greenhouse"
    assert active[0]["board_token"] == "stripe"


def test_invalid_ats_returns_error(tmp_db):
    result = svc.add_company("Acme", "bogusats", "acme")
    assert "error" in result
    assert "bogusats" in result["error"]
    # Nothing was persisted
    assert repo.list_active_watch() == []


def test_set_enabled_false_excludes_from_active(tmp_db):
    result = svc.add_company("Stripe", "greenhouse", "stripe")
    watch_id = result["id"]
    repo.set_watch_enabled(watch_id, False)
    assert repo.list_active_watch() == []
    # Still shows up in full list
    all_watches = repo.list_watch()
    assert len(all_watches) == 1
    assert all_watches[0]["enabled"] is False


def test_remove_watch(tmp_db):
    result = svc.add_company("Stripe", "greenhouse", "stripe")
    svc.remove(result["id"])
    assert repo.list_watch() == []


# ── worker integration tests ───────────────────────────────────────────────


class _StubSource:
    """Stub ATS source for testing run_watchlist()."""

    name = "stub_ats"
    discover_calls: list[dict]

    def __init__(self) -> None:
        self.discover_calls = []

    def discover(
        self,
        *,
        keyword: str,
        location: str = "",
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict:
        """Record the call and return an empty result."""
        self.discover_calls.append({"keyword": keyword, "location": location})
        return {"found": 0, "new": 0, "jobs": []}


def test_run_watchlist_calls_discover(tmp_db, monkeypatch):
    """run_watchlist() calls discover() for each active watch entry."""
    stub = _StubSource()

    def _patched_discover(source: str, *, keyword: str, location: str, **kw: object) -> dict:
        return stub.discover(keyword=keyword, location=location)

    monkeypatch.setattr("job_hunt.worker.runner.discover", _patched_discover)
    repo.add_watch(company="TestCo", ats="greenhouse", board_token="testco-token")
    run_watchlist()
    assert len(stub.discover_calls) == 1
    assert stub.discover_calls[0]["keyword"] == "testco-token"


def test_run_watchlist_skips_disabled(tmp_db, monkeypatch):
    """run_watchlist() skips watch entries that are disabled."""
    stub = _StubSource()

    def _patched_discover(source: str, *, keyword: str, location: str, **kw: object) -> dict:
        return stub.discover(keyword=keyword, location=location)

    monkeypatch.setattr("job_hunt.worker.runner.discover", _patched_discover)
    watch_id = repo.add_watch(company="TestCo", ats="greenhouse", board_token="testco-token")
    repo.set_watch_enabled(watch_id, False)
    run_watchlist()
    assert stub.discover_calls == []


def test_run_watchlist_continues_on_error(tmp_db, monkeypatch):
    """A failing entry does not stop run_watchlist from processing later entries."""
    called: list[str] = []

    def _discover(source: str, *, keyword: str, location: str, **kw: object) -> dict:
        if keyword == "broken-token":
            raise RuntimeError("boom")
        called.append(keyword)
        return {"found": 0, "new": 0, "jobs": []}

    monkeypatch.setattr("job_hunt.worker.runner.discover", _discover)
    svc.add_company("BrokenCo", "ashby", "broken-token")
    svc.add_company("GoodCo", "greenhouse", "good-token")
    run_watchlist()  # must not raise
    assert "good-token" in called
