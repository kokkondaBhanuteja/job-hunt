"""Load `.env.local` / `.env` into the process environment at import time.

Called from `job_hunt/__init__.py` so it runs before any submodule reads env (e.g.
`storage.repo` resolves DB_BACKEND at import). Precedence, highest first:

    real shell exports  >  .env.local  >  .env

i.e. a value already exported in your shell always wins; `.env.local` overrides `.env`.
Skipped under pytest so test fixtures — not your local .env — control the environment.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_LOADED = False
_ROOT = Path(__file__).resolve().parents[1]  # repo root (contains .env / .env.local)


def _apply(path: Path, *, override: bool) -> None:
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # unreadable file must never crash startup — just skip it
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = line.removeprefix("export ").strip()
        key, _, val = line.partition("=")           # split on the FIRST '=' only
        key = key.strip()
        val = val.strip().strip('"').strip("'")      # tolerate quoted values
        if key and (override or key not in os.environ):
            os.environ[key] = val


def load_env_files() -> None:
    """Populate os.environ from .env.local then .env, without clobbering real exports."""
    global _LOADED
    if _LOADED or "pytest" in sys.modules:  # never touch the env during tests
        _LOADED = True
        return
    _LOADED = True
    _apply(_ROOT / ".env.local", override=False)     # .env.local wins over .env
    _apply(_ROOT / ".env", override=False)           # real shell exports win over both
