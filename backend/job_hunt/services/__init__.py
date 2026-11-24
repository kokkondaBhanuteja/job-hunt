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
    funnel_metrics,
    send_daily_report,
    send_test_notification,
    variant_performance,
)
from job_hunt.services.answers import add_answer_template, list_answer_templates, suggest_answer
from job_hunt.services.applicant import extract_applicant, get_applicant, set_applicant
from job_hunt.services.applications import advance_stage, log_application
from job_hunt.services.apply import review_application
from job_hunt.services.apply_policy import get_policy, list_ready_to_apply
from job_hunt.services.brief import brief_for_job
from job_hunt.services.companies import company_history, get_company
from job_hunt.services.content import (
    generate_and_notify_post,
    generate_post,
    list_posts,
    set_post_status,
)
from job_hunt.services.context import get_context, set_context
from job_hunt.services.crm import add_contact, list_contacts
from job_hunt.services.discovery import discover, discover_naukri
from job_hunt.services.drafting import (
    draft_cover_for_job,
    draft_message_for_job,
    draft_outreach_for_job,
    list_drafts,
    tailor_for_job,
)
from job_hunt.services.email_actions import (
    confirm_action,
    dismiss_action,
    propose_action,
)
from job_hunt.services.email_triage import (
    get_email,
    list_inbox,
    structure_pending,
    sync_inbox,
)
from job_hunt.services.enrichment import enrich_pending_jobs
from job_hunt.services.home import home_status
from job_hunt.services.intelligence import explain_score, next_best_action, skill_gap
from job_hunt.services.learning import learn_from_rejection
from job_hunt.services.naukri_refresh import draft_profile_refresh, refresh_reminder
from job_hunt.services.outreach import (
    cancel_outreach,
    draft_due_followups,
    draft_followups_and_notify,
    edit_outreach,
    get_outreach,
    list_outreach,
    record_replies,
    save_outreach_draft,
    send_outreach,
)
from job_hunt.services.profiles import add_profile, list_profiles, set_enabled
from job_hunt.services.resumes import (
    get_variant,
    list_variants,
    parse_resume_vault,
    save_variant_from_text,
)
from job_hunt.services.review import (
    get_job,
    list_board,
    list_resume_vault,
    list_top_matches,
)
from job_hunt.services.runs import get_run, list_runs, request_cancel, run_discovery
from job_hunt.services.scoring import score_pending
from job_hunt.services.search_prefs import get_search_prefs, set_search_prefs
from job_hunt.services.semantic import embed_jobs, semantic_match, similar_successful
from job_hunt.services.watchlist import (
    add_company as add_watch_company,
)
from job_hunt.services.watchlist import (
    list_watch,
)
from job_hunt.services.watchlist import (
    remove as remove_watch,
)
from job_hunt.services.watchlist import (
    set_enabled as set_watch_enabled,
)

__all__ = [
    "brief_for_job",
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
    "funnel_metrics",
    "variant_performance",
    "daily_report_text",
    "send_daily_report",
    "send_test_notification",
    "learn_from_rejection",
    "explain_score",
    "next_best_action",
    "skill_gap",
    "embed_jobs",
    "semantic_match",
    "similar_successful",
    "add_answer_template",
    "list_answer_templates",
    "suggest_answer",
    "review_application",
    "tailor_for_job",
    "draft_cover_for_job",
    "draft_outreach_for_job",
    "draft_message_for_job",
    "list_drafts",
    "add_contact",
    "list_contacts",
    "save_outreach_draft",
    "list_outreach",
    "get_outreach",
    "edit_outreach",
    "send_outreach",
    "cancel_outreach",
    "draft_due_followups",
    "draft_followups_and_notify",
    "record_replies",
    "get_company",
    "company_history",
    "set_context",
    "get_context",
    "set_search_prefs",
    "get_search_prefs",
    "set_applicant",
    "get_applicant",
    "extract_applicant",
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
    "generate_post",
    "list_posts",
    "set_post_status",
    "generate_and_notify_post",
    "draft_profile_refresh",
    "refresh_reminder",
    "get_policy",
    "list_ready_to_apply",
    "add_watch_company",
    "list_watch",
    "set_watch_enabled",
    "remove_watch",
    "save_variant_from_text",
    "get_variant",
    "list_variants",
    "home_status",
]
