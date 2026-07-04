"""Shared service layer — the architectural keystone.

Every entrypoint (CLI, MCP server, and later the FastAPI app + worker) calls these
functions instead of reaching into modules directly. Business logic and `init_db()`
calls live here; entrypoints stay thin adapters. Services return plain dicts/lists
(never argparse/FastMCP/FastAPI types).
"""
from __future__ import annotations

from job_hunt.apply.formfill import prepare_form_fill
from job_hunt.services.analytics import (
    daily_report_text,
    dashboard,
    send_daily_report,
    variant_performance,
)
from job_hunt.services.answers import add_answer_template, list_answer_templates, suggest_answer
from job_hunt.services.applicant import get_applicant, set_applicant
from job_hunt.services.applications import advance_stage, log_application
from job_hunt.services.apply import review_application
from job_hunt.services.companies import company_history, get_company
from job_hunt.services.context import get_context, set_context
from job_hunt.services.crm import add_contact, list_contacts
from job_hunt.services.discovery import discover, discover_naukri
from job_hunt.services.drafting import (
    draft_cover_for_job,
    draft_outreach_for_job,
    list_drafts,
    tailor_for_job,
)
from job_hunt.services.email_triage import (
    confirm_action,
    dismiss_action,
    get_email,
    list_inbox,
    propose_action,
    structure_pending,
    sync_inbox,
)
from job_hunt.services.enrichment import enrich_pending_jobs
from job_hunt.services.learning import learn_from_rejection
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
from job_hunt.services.semantic import embed_jobs, semantic_match

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
    "daily_report_text",
    "send_daily_report",
    "learn_from_rejection",
    "embed_jobs",
    "semantic_match",
    "add_answer_template",
    "list_answer_templates",
    "suggest_answer",
    "review_application",
    "tailor_for_job",
    "draft_cover_for_job",
    "draft_outreach_for_job",
    "list_drafts",
    "add_contact",
    "list_contacts",
    "get_company",
    "company_history",
    "set_context",
    "get_context",
    "set_applicant",
    "get_applicant",
    "parse_resume_vault",
    "add_profile",
    "list_profiles",
    "set_enabled",
    "list_runs",
    "get_run",
    "request_cancel",
    "run_discovery",
    "prepare_form_fill",
    "sync_inbox",
    "structure_pending",
    "list_inbox",
    "get_email",
    "propose_action",
    "confirm_action",
    "dismiss_action",
]
