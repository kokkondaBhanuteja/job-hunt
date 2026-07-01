"""Central logging setup — one leveled, timestamped stderr handler under the `job_hunt`
logger tree. Call `get_logger(__name__)` in library modules; configuration is lazy and
idempotent so importing a module never emits output until something actually logs.

Level via `LOG_LEVEL` env (default INFO). CLI user-facing output still uses `print`;
this is for operational/diagnostic logging (worker, services, LLM, scrapers).
"""
from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger("job_hunt")
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Module logger under the `job_hunt` tree (configures the tree on first call)."""
    _configure()
    return logging.getLogger(name if name.startswith("job_hunt") else f"job_hunt.{name}")
