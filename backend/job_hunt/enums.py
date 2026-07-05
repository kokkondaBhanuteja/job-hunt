"""Canonical enums + constants for the toolkit.

Single source of truth for the string values that flow through the DB, services,
LLM registry, and (later) the API. Using `StrEnum` means members compare/serialize
as their string value, so they drop straight into SQL params, dict payloads, and
JSON without conversion — while giving one place to change a value.

The SQLite schema derives its `CHECK (... IN (...))` constraints from these enums
via `sql_in_list()`, so the allowed values in the database can never drift from the
allowed values in code.
"""
from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Lifecycle status stored on `jobs.status` (v0 set; the full state machine lands in P1)."""

    NEW = "new"
    READY_TO_REVIEW = "ready-to-review"
    APPLIED = "applied"
    SKIPPED = "skipped"
    SAVED = "saved"


class ApplicationOutcome(StrEnum):
    """Outcome the user logs against a job via `log_application`."""

    APPLIED = "applied"
    SKIPPED = "skipped"
    SAVED = "saved"


class ReplyType(StrEnum):
    """Recruiter reply classification stored on `applications.reply_type`."""

    INTERVIEW = "interview"
    REJECT = "reject"
    NEXT_STEP = "next-step"


class ApplicationStage(StrEnum):
    """Interview-pipeline stage stored on `applications.stage` — powers the funnel."""

    APPLIED = "applied"
    OA = "oa"
    INTERVIEW = "interview"
    HR = "hr"
    OFFER = "offer"
    REJECTED = "rejected"


class LLMTask(StrEnum):
    """A unit of work routed to a configured provider/model (see llm/registry.py)."""

    SCORING = "scoring"
    DRAFTING = "drafting"
    TAILORING = "tailoring"
    EMAIL_STRUCTURE = "email_structure"


class EmailCategory(StrEnum):
    """Category classification of an inbound email — determines triage and suggested actions."""

    RECRUITER_OUTREACH = "recruiter_outreach"
    INTERVIEW_INVITE = "interview_invite"
    REJECTION = "rejection"
    APPLICATION_CONFIRMATION = "application_confirmation"
    OTHER = "other"


class EmailActionState(StrEnum):
    """Lifecycle state of a suggested action on an email."""

    NONE = "none"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    FAILED = "failed"
    DISMISSED = "dismissed"


class EmailActionKind(StrEnum):
    """Kind of action suggested or taken on an email."""

    DRAFT_REPLY = "draft_reply"
    APPLY_LABEL = "apply_label"
    ARCHIVE = "archive"


class PostStatus(StrEnum):
    """Lifecycle status of an AI-drafted tech post — never auto-posted."""

    DRAFT = "draft"
    POSTED = "posted"
    DISMISSED = "dismissed"


class LLMProvider(StrEnum):
    """Supported LLM backends."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    GEMINI = "gemini"
    GROQ = "groq"
    STUB = "stub"


class ScrapeStatus(StrEnum):
    """Health of a single scrape pass — distinguishes 'blocked' from 'genuinely empty'."""

    OK = "ok"            # cards found as expected
    EMPTY = "empty"      # zero results where some were expected (suspicious)
    BLOCKED = "blocked"  # login wall / captcha / anti-bot challenge detected


class DraftKind(StrEnum):
    """Kind of generated draft stored in `drafts`."""

    COVER = "cover"
    OUTREACH = "outreach"
    THANK_YOU = "thank_you"
    FOLLOW_UP = "follow_up"
    NEGOTIATION = "negotiation"


class ContextFormat(StrEnum):
    """Format the user supplies their career context in (stored verbatim, injected as-is)."""

    MD = "md"
    JSON = "json"


class LearningKind(StrEnum):
    """What an outcome taught us, stored on `learnings`."""

    REJECTION = "rejection"       # JD requirements the resume under-emphasized
    INTERVIEW = "interview"       # a variant that won an interview
    EXPLANATION = "explanation"   # score breakdown: matched/missing/suggestions


class ATSPlatform(StrEnum):
    """Applicant-tracking system behind a job's apply page — picks the apply flow."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    ICIMS = "icims"
    NAUKRI = "naukri"
    REMOTEOK = "remoteok"
    UNKNOWN = "unknown"


class JobState(StrEnum):
    """Explicit lifecycle state on `jobs.state` (the state machine; supersedes the
    coarse `jobs.status` over time). Transitions are validated + audited + emit events."""

    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    SCORED = "scored"
    ARCHIVED = "archived"              # below threshold / filtered out
    TAILORING_READY = "tailoring_ready"   # a tailored résumé exists
    DRAFTED = "drafted"                   # a cover letter / outreach exists
    REVIEW_PENDING = "review_pending"     # application package assembled, awaiting your review
    APPLIED = "applied"
    OA = "oa"
    INTERVIEW = "interview"
    HR = "hr"
    OFFER = "offer"
    REJECTED = "rejected"
    DEFERRED = "deferred"              # wait / referral / salary-unknown
    WITHDRAWN = "withdrawn"


# States that are applied/closed/parked — excluded from "top matches to act on now".
# (top-matches also requires a score via the join, so this is effectively "scored & live".)
CLOSED_STATES: tuple[JobState, ...] = (
    JobState.APPLIED, JobState.OA, JobState.INTERVIEW, JobState.HR, JobState.OFFER,
    JobState.REJECTED, JobState.ARCHIVED, JobState.WITHDRAWN, JobState.DEFERRED,
)


class RunStatus(StrEnum):
    """Lifecycle of a background run (discovery/scoring/apply)."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLED = "cancelled"
    FAILED = "failed"
    DONE = "done"


class EventClass(StrEnum):
    """Domain events drive analytics/automation; infra events are monitoring-only."""

    DOMAIN = "domain"
    INFRA = "infra"


class EventType(StrEnum):
    """The ~7 MAJOR domain transitions (kept deliberately small) + infra signals."""

    # domain
    JOB_DISCOVERED = "job.discovered"
    JOB_ENRICHED = "job.enriched"
    JOB_SCORED = "job.scored"
    RESUME_TAILORED = "resume.tailored"
    DRAFT_GENERATED = "draft.generated"
    APPLICATION_SUBMITTED = "application.submitted"
    INTERVIEW_UPDATED = "interview.updated"
    # infra
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    SCRAPE_BLOCKED = "scrape.blocked"
    RATE_LIMIT_REACHED = "rate_limit.reached"


# Legacy: job *statuses* considered open (jobs.status is retired in favor of jobs.state).
REVIEWABLE_STATUSES: tuple[JobStatus, ...] = (JobStatus.NEW, JobStatus.READY_TO_REVIEW)

# jobs.state values that are "scored + still worth reviewing/acting on" (top-matches).
# Defined lazily below once JobState exists.


# Score thresholds (0-100). Centralized so tuning happens in one place.
class Score:
    DEFAULT_MIN_MATCH = 70   # default floor for "show me matches"
    APPLY_THRESHOLD = 80     # only act/apply at or above this (P6)
    STRONG = 85


def sql_in_list(enum_cls: type[StrEnum]) -> str:
    """Render an enum as a SQL value list for `CHECK (col IN (...))` / `WHERE col IN (...)`.

    e.g. ``sql_in_list(JobStatus)`` -> ``'new', 'ready-to-review', 'applied', 'skipped', 'saved'``.
    Values are enum-controlled (never user input), so simple quoting is safe.
    """
    return ", ".join(f"'{member.value}'" for member in enum_cls)


def sql_values(members: tuple[StrEnum, ...]) -> str:
    """Render a specific tuple of enum members as a SQL value list."""
    return ", ".join(f"'{m.value}'" for m in members)
