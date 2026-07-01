"""Shared service layer — the architectural keystone.

Every entrypoint (CLI, MCP server, and later the FastAPI app + worker) calls these
functions instead of reaching into modules directly. Business logic and `init_db()`
calls live here; entrypoints stay thin adapters. Services return plain dicts/lists
(never argparse/FastMCP/FastAPI types).
"""
from __future__ import annotations

from job_hunt.services.applications import log_application
from job_hunt.services.discovery import discover_naukri
from job_hunt.services.profiles import add_profile, list_profiles, set_enabled
from job_hunt.services.resumes import parse_resume_vault
from job_hunt.services.review import (
    get_job,
    list_board,
    list_resume_vault,
    list_top_matches,
)
from job_hunt.services.runs import get_run, list_runs, request_cancel, run_discovery
from job_hunt.services.scoring import score_pending

__all__ = [
    "discover_naukri",
    "score_pending",
    "list_top_matches",
    "list_board",
    "get_job",
    "list_resume_vault",
    "log_application",
    "parse_resume_vault",
    "add_profile",
    "list_profiles",
    "set_enabled",
    "list_runs",
    "get_run",
    "request_cancel",
    "run_discovery",
]
