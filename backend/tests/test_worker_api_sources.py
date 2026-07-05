"""Tests for run_api_sources — API source polling across active search profiles."""
from __future__ import annotations

from job_hunt import services
from job_hunt.plugins.base import register
from job_hunt.worker import config, runner


class _StubApiSource:
    """Minimal stub that records discover() calls without hitting the network."""

    name = "stub"

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def discover(
        self,
        *,
        keyword: str,
        location: str,
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, object]:
        """Record args and return a minimal success payload."""
        self.calls.append({"keyword": keyword, "location": location})
        return {"found": 1, "new": 1, "jobs": []}


def test_run_api_sources_calls_stub_per_profile(tmp_db, monkeypatch):
    """Stub discover is called once per active profile with the profile's keywords/location."""
    stub = _StubApiSource()
    register(stub)
    monkeypatch.setattr(config, "API_SOURCES", ["stub"])

    services.add_profile(name="py-blr", keywords="python", location="bangalore", pages=1)

    runner.run_api_sources()

    assert len(stub.calls) == 1
    assert stub.calls[0]["keyword"] == "python"
    assert stub.calls[0]["location"] == "bangalore"


def test_run_api_sources_calls_once_per_profile(tmp_db, monkeypatch):
    """With multiple profiles each gets its own discover call."""
    stub = _StubApiSource()
    register(stub)
    monkeypatch.setattr(config, "API_SOURCES", ["stub"])

    services.add_profile(name="py-blr", keywords="python", location="bangalore", pages=1)
    services.add_profile(name="go-mum", keywords="golang", location="mumbai", pages=1)

    runner.run_api_sources()

    assert len(stub.calls) == 2
    keywords_seen = {c["keyword"] for c in stub.calls}
    assert keywords_seen == {"python", "golang"}


def test_run_api_sources_skips_unregistered_source(tmp_db, monkeypatch):
    """An unregistered source name in API_SOURCES is skipped without raising."""
    monkeypatch.setattr(config, "API_SOURCES", ["definitely-not-registered"])

    services.add_profile(name="py-blr", keywords="python", location="bangalore", pages=1)

    # Must not raise; graceful skip.
    runner.run_api_sources()


def test_run_api_sources_no_profiles_is_noop(tmp_db, monkeypatch):
    """When there are no active profiles, run_api_sources completes without error."""
    stub = _StubApiSource()
    register(stub)
    monkeypatch.setattr(config, "API_SOURCES", ["stub"])

    runner.run_api_sources()

    assert stub.calls == []
