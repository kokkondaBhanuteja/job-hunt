"""Storage backend façade — the single import point for persistence.

Selects the backend from the `DB_BACKEND` env var (default `sqlite`):
  - `sqlite`   → job_hunt.storage.db   (fast, zero-infra; the test path)
  - `postgres` → job_hunt.storage.pg   (psycopg3; the production datastore)

Both modules expose the same function surface, so every caller (services, scoring,
resume parsing, LLM logging, CLI) imports from here and is backend-agnostic.
"""
from __future__ import annotations

import os

_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()

if _BACKEND in ("postgres", "pg", "postgresql"):
    from job_hunt.storage import pg as _impl
    backend = "postgres"
else:
    from job_hunt.storage import db as _impl
    backend = "sqlite"

# Re-export the shared repository surface.
init_db = _impl.init_db
describe = _impl.describe
raw_select = _impl.raw_select

insert_job_if_new = _impl.insert_job_if_new
upsert_resume_variant = _impl.upsert_resume_variant
write_score = _impl.write_score
write_llm_call = _impl.write_llm_call
record_application = _impl.record_application
set_application_stage = _impl.set_application_stage

list_resume_variants = _impl.list_resume_variants
list_scorable_jobs = _impl.list_scorable_jobs
list_board_jobs = _impl.list_board_jobs
top_matches = _impl.top_matches
get_job = _impl.get_job
list_scores_for_job = _impl.list_scores_for_job
scores_meta_for_job = _impl.scores_meta_for_job
scores_meta_for_jobs = _impl.scores_meta_for_jobs
find_variant_id_by_slug = _impl.find_variant_id_by_slug
set_job_enriched = _impl.set_job_enriched

# drafting
best_scored_variant = _impl.best_scored_variant
save_tailored_resume = _impl.save_tailored_resume
get_tailored_resume = _impl.get_tailored_resume
save_draft = _impl.save_draft
list_drafts_for_job = _impl.list_drafts_for_job
save_learning = _impl.save_learning
list_learnings_for_job = _impl.list_learnings_for_job
save_answer_template = _impl.save_answer_template
list_answer_templates = _impl.list_answer_templates
save_contact = _impl.save_contact
list_contacts = _impl.list_contacts
get_company = _impl.get_company
company_history = _impl.company_history

# embeddings (Postgres only)
set_job_embedding = _impl.set_job_embedding
set_variant_embedding = _impl.set_variant_embedding
jobs_missing_embedding = _impl.jobs_missing_embedding
semantic_jobs = _impl.semantic_jobs

# state machine
get_job_state = _impl.get_job_state
set_job_state = _impl.set_job_state
write_job_transition = _impl.write_job_transition
apply_transition = _impl.apply_transition

# event outbox
write_event = _impl.write_event
fetch_unprocessed_events = _impl.fetch_unprocessed_events
mark_event_processed = _impl.mark_event_processed
record_event_failure = _impl.record_event_failure

# runs
create_run = _impl.create_run
start_run = _impl.start_run
heartbeat_run = _impl.heartbeat_run
finish_run = _impl.finish_run
request_run_cancel = _impl.request_run_cancel
run_cancel_requested = _impl.run_cancel_requested
append_run_log = _impl.append_run_log
get_run = _impl.get_run
list_recent_runs = _impl.list_recent_runs
count_runs_today = _impl.count_runs_today
reap_stale_runs = _impl.reap_stale_runs

# search profiles
set_user_context = _impl.set_user_context
get_user_context = _impl.get_user_context

# applicant profile
set_applicant_profile = _impl.set_applicant_profile
get_applicant_profile = _impl.get_applicant_profile

create_search_profile = _impl.create_search_profile
list_search_profiles = _impl.list_search_profiles
list_active_search_profiles = _impl.list_active_search_profiles
get_search_profile = _impl.get_search_profile
set_search_profile_enabled = _impl.set_search_profile_enabled

# email triage
upsert_email_message = _impl.upsert_email_message
set_email_structured = _impl.set_email_structured
set_email_links = _impl.set_email_links
set_email_action_state = _impl.set_email_action_state
get_email_message = _impl.get_email_message
list_email_messages = _impl.list_email_messages
list_unstructured_emails = _impl.list_unstructured_emails
get_sync_state = _impl.get_sync_state
set_sync_state = _impl.set_sync_state
get_application_by_job = _impl.get_application_by_job

# email actions
create_email_action = _impl.create_email_action
get_email_action = _impl.get_email_action
get_latest_action_for_email = _impl.get_latest_action_for_email
set_email_action_result = _impl.set_email_action_result
