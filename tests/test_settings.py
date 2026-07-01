"""F: config is validated at startup — a bad env var fails fast with a clear message."""
from __future__ import annotations

import pytest

from job_hunt.settings import Settings, validate_settings


def test_defaults_are_valid(monkeypatch):
    for var in ("DB_BACKEND", "WORKER_DAILY_CAP", "LOG_LEVEL", "WORKER_ACTIVE_START",
                "LLM_SCORING_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    s = validate_settings()
    assert s.db_backend == "sqlite" and s.daily_cap == 30


def test_bad_db_backend_fails_fast(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "mysql")
    with pytest.raises(SystemExit, match="DB_BACKEND"):
        validate_settings()


def test_non_positive_cap_and_bad_cap_fail(monkeypatch):
    monkeypatch.setenv("WORKER_DAILY_CAP", "0")
    with pytest.raises(SystemExit, match="DAILY_CAP"):
        validate_settings()
    monkeypatch.setenv("WORKER_DAILY_CAP", "lots")
    with pytest.raises(SystemExit, match="integer"):
        validate_settings()


def test_bad_llm_provider_fails(monkeypatch):
    monkeypatch.setenv("LLM_SCORING_PROVIDER", "anthropic-typo")
    with pytest.raises(SystemExit, match="LLM_SCORING_PROVIDER"):
        validate_settings()


def test_bad_active_hours_fail(monkeypatch):
    monkeypatch.setenv("WORKER_ACTIVE_START", "9am")
    with pytest.raises(SystemExit, match="HH:MM"):
        validate_settings()


def test_valid_overrides_accepted(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "postgres")
    monkeypatch.setenv("LLM_SCORING_PROVIDER", "openai")
    monkeypatch.setenv("WORKER_DAILY_CAP", "50")
    s = Settings.from_env()
    assert s.db_backend == "postgres" and s.llm_providers["scoring"] == "openai" and s.daily_cap == 50
