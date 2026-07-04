"""Central configuration — read from env, validated at startup so a typo fails FAST with a
clear message instead of surfacing as a mysterious error on first query / first crawl.

`validate_settings()` is called by the long-running entrypoints (`serve-api`, `worker`).
Individual modules still read their own env at call time; this is the fail-fast gate, not a
forced rewrite of every `os.getenv`.
"""
from __future__ import annotations

import os
import re

from pydantic import BaseModel, ValidationError, field_validator

from job_hunt.enums import LLMProvider

_HHMM = re.compile(r"^\d{1,2}:\d{2}$")
_TASKS = ("scoring", "drafting", "tailoring", "email_structure")
_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}


class Settings(BaseModel):
    db_backend: str = "sqlite"
    database_url: str | None = None
    api_token: str | None = None
    log_level: str = "INFO"
    active_start: str = "09:30"
    active_end: str = "21:00"
    daily_cap: int = 30
    llm_providers: dict[str, str] = {}  # task -> provider (only tasks with an override set)

    @field_validator("db_backend")
    @classmethod
    def _backend(cls, v: str) -> str:
        if v not in ("sqlite", "postgres"):
            raise ValueError(f"DB_BACKEND must be 'sqlite' or 'postgres', got '{v}'")
        return v

    @field_validator("log_level")
    @classmethod
    def _level(cls, v: str) -> str:
        if v.upper() not in _LEVELS:
            raise ValueError(f"LOG_LEVEL '{v}' invalid (use one of {sorted(_LEVELS)})")
        return v.upper()

    @field_validator("active_start", "active_end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError(f"active-hours must be HH:MM, got '{v}'")
        return v

    @field_validator("daily_cap")
    @classmethod
    def _cap(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"WORKER_DAILY_CAP must be > 0, got {v}")
        return v

    @field_validator("llm_providers")
    @classmethod
    def _providers(cls, v: dict[str, str]) -> dict[str, str]:
        allowed = {p.value for p in LLMProvider}
        for task, provider in v.items():
            if provider not in allowed:
                raise ValueError(
                    f"LLM_{task.upper()}_PROVIDER '{provider}' invalid (use {sorted(allowed)})"
                )
        return v

    @classmethod
    def from_env(cls) -> Settings:
        cap_raw = os.getenv("WORKER_DAILY_CAP", "30")
        try:
            cap = int(cap_raw)
        except ValueError:
            raise ValueError(f"WORKER_DAILY_CAP must be an integer, got '{cap_raw}'") from None
        providers = {t: os.getenv(f"LLM_{t.upper()}_PROVIDER") for t in _TASKS}

        # Validate EMAIL_* credentials: all-or-none constraint
        email_host = os.getenv("EMAIL_IMAP_HOST")
        email_address = os.getenv("EMAIL_ADDRESS")
        email_password = os.getenv("EMAIL_APP_PASSWORD")
        email_vars = [email_host, email_address, email_password]
        email_set_count = sum(1 for v in email_vars if v)
        if email_set_count > 0 and email_set_count < 3:
            raise ValueError(
                "EMAIL_* config incomplete: set all of EMAIL_IMAP_HOST, EMAIL_ADDRESS, "
                "EMAIL_APP_PASSWORD or none"
            )

        return cls(
            db_backend=os.getenv("DB_BACKEND", "sqlite"),
            database_url=os.getenv("DATABASE_URL"),
            api_token=os.getenv("API_TOKEN"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            active_start=os.getenv("WORKER_ACTIVE_START", "09:30"),
            active_end=os.getenv("WORKER_ACTIVE_END", "21:00"),
            daily_cap=cap,
            llm_providers={t: p for t, p in providers.items() if p},
        )


def validate_settings() -> Settings:
    """Load + validate config from env. Raises SystemExit with a clear message on misconfig."""
    try:
        return Settings.from_env()
    except (ValidationError, ValueError) as exc:
        raise SystemExit(f"Invalid configuration — fix the env var(s):\n{exc}") from None
