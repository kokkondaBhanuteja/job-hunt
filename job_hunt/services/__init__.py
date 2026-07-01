"""Shared service layer — the architectural keystone.

Every entrypoint (CLI, MCP server, and later the FastAPI app + worker) calls these
functions instead of reaching into modules directly. Business logic and `init_db()`
calls live here; entrypoints stay thin adapters. Services return plain dicts/lists
(never argparse/FastMCP/FastAPI types).
"""
from __future__ import annotations

from job_hunt.services.analytics import dashboard, variant_performance
from job_hunt.services.answers import add_answer_template, list_answer_templates, suggest_answer
from job_hunt.services.applications import advance_stage, log_application
from job_hunt.services.learning import learn_from_rejection
from job_hunt.services.apply import (
    prepare_application,
    record_submitted_resume,
    review_application,
)
from job_hunt.services.companies import company_history, get_company, upsert_company
from job_hunt.services.crm import add_contact, list_contacts
from job_hunt.services.discovery import discover, discover_naukri
from job_hunt.services.drafting import (
    draft_cover_for_job,
    draft_outreach_for_job,
    list_drafts,
    tailor_for_job,
)
from job_hunt.services.enrichment import enrich_pending_jobs
from job_hunt.services.profiles import add_profile, list_profiles, set_enabled
from job_hunt.services.resumes import parse_resume_vault
from job_hunt.services.review import (
    get_job,
    list_board,
    list_resume_vault,
    list_top_matches,
)
from job_hunt.services.semantic import embed_jobs, semantic_match
from job_hunt.services.runs import get_run, list_runs, request_cancel, run_discovery
from job_hunt.services.scoring import score_pending

__all__ = [
    "discover",
    "discover_naukri",
    "enrich_pending_jobs",
    "score_pending",
    "list_top_matches",
    "list_board",
    "get_job",
    "list_resume_vault",
    "log_application",
    "advance_stage",
    "dashboard",
    "variant_performance",
    "learn_from_rejection",
    "embed_jobs",
    "semantic_match",
    "add_answer_template",
    "list_answer_templates",
    "suggest_answer",
    "review_application",
    "prepare_application",
    "record_submitted_resume",
    "tailor_for_job",
    "draft_cover_for_job",
    "draft_outreach_for_job",
    "list_drafts",
    "add_contact",
    "list_contacts",
    "upsert_company",
    "get_company",
    "company_history",
    "parse_resume_vault",
    "add_profile",
    "list_profiles",
    "set_enabled",
    "list_runs",
    "get_run",
    "request_cancel",
    "run_discovery",
]
