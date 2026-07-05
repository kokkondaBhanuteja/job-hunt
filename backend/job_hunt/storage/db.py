"""
SQLite storage layer. All toolkit state lives in data/jobhunt.db.

Why SQLite (not Mongo / Postgres):
- single-user personal tool — zero ops
- one file you can `cp` to back up
- DB Browser for SQLite gives a free GUI for ad-hoc inspection
- no cloud IPs / no credentials / no expiring tokens

Schema is intentionally light:
- resume_variants:  the user's hand-maintained LaTeX resumes, parsed to JSON
- jobs:             every job discovered (deduped by hash)
- scores:           one row per (job, variant) — qwen's fit score + reasoning
- applications:     a job we actually applied to (or skipped, or saved)
- contacts:         HRs/recruiters/etc. extracted from JDs / company pages
- outreach:         outreach messages drafted (mailto URLs)
- runs:             one row per pipeline run (for run history / debugging)
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from job_hunt.enums import (
    CLOSED_STATES,
    ApplicationStage,
    ContextFormat,
    DraftKind,
    EmailActionKind,
    EmailActionState,
    EmailCategory,
    EventClass,
    EventType,
    JobState,
    JobStatus,
    ReplyType,
    RunStatus,
    sql_in_list,
    sql_values,
)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "jobhunt.db"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS resume_variants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT UNIQUE NOT NULL,        -- e.g. 'backend-node'
    source_path     TEXT NOT NULL,                -- path to the .tex file
    parsed_json     TEXT NOT NULL,                -- structured resume as JSON
    tags            TEXT NOT NULL,                -- JSON array of tags, e.g. ["nestjs","aws"]
    updated_at      TEXT NOT NULL                 -- ISO8601 UTC
);

CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_hash      TEXT UNIQUE NOT NULL,         -- sha1(company|normalized_title)
    source          TEXT NOT NULL,                -- 'naukri' | 'foundit' | 'greenhouse' | ...
    source_job_id   TEXT,                          -- the site's own id, if any
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT,
    description     TEXT,                          -- listing snippet
    description_full TEXT,                          -- full JD text (from the enrich step)
    enriched_at     TEXT,                           -- ISO8601 UTC when the full JD was fetched
    apply_url       TEXT NOT NULL,
    posted_date     TEXT,
    discovered_at   TEXT NOT NULL,                 -- ISO8601 UTC
    raw_payload     TEXT,                          -- JSON: anything else the scraper grabbed
    status          TEXT NOT NULL DEFAULT '{JobStatus.NEW}'
                        CHECK (status IN ({sql_in_list(JobStatus)})),
    state           TEXT NOT NULL DEFAULT '{JobState.DISCOVERED}'
                        CHECK (state IN ({sql_in_list(JobState)}))
);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);

CREATE TABLE IF NOT EXISTS scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id      INTEGER NOT NULL REFERENCES resume_variants(id) ON DELETE CASCADE,
    fit_score       INTEGER NOT NULL,             -- 0-100
    confidence      INTEGER,                       -- 0-100; how sure the model is (low when JD incomplete)
    reasoning       TEXT NOT NULL,                -- short paragraph
    scored_against  TEXT,                          -- 'snippet' | 'full' — which JD text was scored
    input_hash      TEXT,                          -- hash of the JD text used (idempotency)
    provider_model  TEXT,                          -- provider/model that produced the score
    scored_at       TEXT NOT NULL,                -- ISO8601 UTC
    UNIQUE(job_id, variant_id)
);
CREATE INDEX IF NOT EXISTS idx_scores_job ON scores(job_id);
CREATE INDEX IF NOT EXISTS idx_scores_fit ON scores(fit_score DESC);
CREATE INDEX IF NOT EXISTS idx_scores_variant ON scores(variant_id);

CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id      INTEGER NOT NULL REFERENCES resume_variants(id),
    cover_letter    TEXT NOT NULL,
    applied_at      TEXT NOT NULL,
    reply_type      TEXT CHECK (reply_type IS NULL OR reply_type IN ({sql_in_list(ReplyType)})),
    reply_notes     TEXT,
    stage           TEXT NOT NULL DEFAULT '{ApplicationStage.APPLIED}'
                        CHECK (stage IN ({sql_in_list(ApplicationStage)})),
    UNIQUE(job_id)
);
CREATE INDEX IF NOT EXISTS idx_applications_variant ON applications(variant_id);

CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT,
    persona         TEXT,                          -- 'HR' | 'Recruiter' | 'EM' | 'IC' | 'Founder'
    email_guess     TEXT,                          -- the permutation we ended up using
    linkedin_url    TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(company, name)
);

CREATE TABLE IF NOT EXISTS outreach (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id      INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    job_id          INTEGER REFERENCES jobs(id),
    template_slug   TEXT NOT NULL,
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,
    mailto_url      TEXT NOT NULL,
    drafted_at      TEXT NOT NULL,
    sent_at         TEXT                            -- you set this when you click Send
);

CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    sources          TEXT NOT NULL,                  -- JSON list of source slugs run
    jobs_found       INTEGER NOT NULL DEFAULT 0,
    jobs_new         INTEGER NOT NULL DEFAULT 0,
    errors           TEXT,                            -- JSON
    status           TEXT NOT NULL DEFAULT '{RunStatus.QUEUED}'
                         CHECK (status IN ({sql_in_list(RunStatus)})),
    heartbeat_at     TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,      -- cooperative cancel flag
    log              TEXT NOT NULL DEFAULT ''
);

-- Job state-machine audit trail (every transition, who/why).
CREATE TABLE IF NOT EXISTS job_transitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    from_state  TEXT,                                 -- NULL for the initial state
    to_state    TEXT NOT NULL,
    reason      TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_transitions_job ON job_transitions(job_id);

-- In-DB event outbox (the event bus). class = domain | infra.
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    type         TEXT NOT NULL,
    class        TEXT NOT NULL,
    payload      TEXT,                                -- JSON
    created_at   TEXT NOT NULL,
    processed_at TEXT,                                -- NULL until the worker handles it
    retry_count  INTEGER NOT NULL DEFAULT 0,          -- handler failures so far
    dead_at      TEXT                                 -- set when dead-lettered (stops blocking)
);
CREATE INDEX IF NOT EXISTS idx_events_unprocessed ON events(processed_at) WHERE processed_at IS NULL;

-- Company research cache + memory (history is derived from jobs/applications).
CREATE TABLE IF NOT EXISTS companies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    size          TEXT,
    funding_stage TEXT,
    tech          TEXT,                            -- JSON array
    glassdoor     TEXT,
    notes         TEXT,
    fetched_at    TEXT
);

-- Reusable, truthful screening-question answers (drawn from during apply form-fill).
CREATE TABLE IF NOT EXISTS answer_templates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    question_pattern TEXT NOT NULL,                 -- e.g. "why do you want to join"
    answer_text      TEXT NOT NULL,
    tags             TEXT,                           -- JSON array
    created_at       TEXT NOT NULL
);

-- The user's single career-context blob (pasted md/json), injected into every AI prompt.
CREATE TABLE IF NOT EXISTS user_context (
    id         INTEGER PRIMARY KEY CHECK (id = 1),   -- singleton: one active context
    content    TEXT NOT NULL,
    format     TEXT NOT NULL CHECK (format IN ({sql_in_list(ContextFormat)})),
    updated_at TEXT NOT NULL
);

-- The user's job-search preferences (pasted md), parsed by the LLM into search profiles.
CREATE TABLE IF NOT EXISTS search_prefs (
    id         INTEGER PRIMARY KEY CHECK (id = 1),   -- singleton: one active prefs blob
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Standing application answers a résumé does not carry (single active row).
CREATE TABLE IF NOT EXISTS applicant_profile (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    first_name          TEXT,
    last_name           TEXT,
    email               TEXT,
    phone               TEXT,
    location            TEXT,
    linkedin_url        TEXT,
    github_url          TEXT,
    portfolio_url       TEXT,
    work_authorization  TEXT,
    needs_sponsorship   INTEGER,
    willing_to_relocate INTEGER,
    notice_period       TEXT,
    expected_ctc        TEXT,
    current_ctc         TEXT,
    years_experience    TEXT,
    referral_source     TEXT,
    extra               TEXT,          -- JSON: {{question_pattern: answer}}
    updated_at          TEXT NOT NULL
);

-- What outcomes taught us (feeds future tailoring / variant preference).
CREATE TABLE IF NOT EXISTS learnings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id  INTEGER REFERENCES resume_variants(id),
    kind        TEXT NOT NULL,                  -- 'rejection' | 'interview'
    payload     TEXT,                            -- JSON: missing_keywords + summary
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learnings_job ON learnings(job_id);

-- Tailored resume per (job, variant) — LLM-emphasized, invents nothing.
CREATE TABLE IF NOT EXISTS tailored_resumes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id  INTEGER NOT NULL REFERENCES resume_variants(id),
    content     TEXT NOT NULL,                  -- tailored resume (markdown)
    created_at  TEXT NOT NULL,
    UNIQUE(job_id, variant_id)
);

-- Resumable progress of a multi-page application (crash recovery).
CREATE TABLE IF NOT EXISTS apply_checkpoints (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step       INTEGER NOT NULL,               -- last completed step index
    data       TEXT,                            -- JSON: accumulated fill state
    updated_at TEXT NOT NULL,
    UNIQUE(job_id)
);

-- Immutable snapshot of exactly what résumé was submitted (answers "which got interviews?").
CREATE TABLE IF NOT EXISTS submitted_resumes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id   INTEGER REFERENCES resume_variants(id),
    content      TEXT NOT NULL,
    submitted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_submitted_job ON submitted_resumes(job_id);
CREATE INDEX IF NOT EXISTS idx_submitted_variant ON submitted_resumes(variant_id);

-- Generated drafts: cover letters + recruiter outreach.
CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ({sql_in_list(DraftKind)})),
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',   -- draft | accepted
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_job ON drafts(job_id);

-- Saved searches. Discovery runs once per ACTIVE profile.
CREATE TABLE IF NOT EXISTS search_profiles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT UNIQUE NOT NULL,
    keywords          TEXT NOT NULL,
    location          TEXT NOT NULL,
    pages             INTEGER NOT NULL DEFAULT 1,
    exclusions        TEXT,                          -- JSON array of title keywords to skip
    min_salary        INTEGER,
    companies_include TEXT,                          -- JSON array
    companies_exclude TEXT,                          -- JSON array
    remote_only       INTEGER NOT NULL DEFAULT 0,
    min_yoe           INTEGER,
    enabled           INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL
);

-- Observability: one row per LLM call (any provider). Powers debugging + the
-- future cost dashboard. Logging is best-effort and never blocks a chat call.
CREATE TABLE IF NOT EXISTS llm_calls (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    task              TEXT NOT NULL,                -- 'scoring' | 'drafting' | 'tailoring' | ...
    provider          TEXT NOT NULL,                -- 'ollama' | 'openai' | 'gemini' | 'stub'
    model             TEXT NOT NULL,
    prompt            TEXT,
    response          TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost              REAL,                          -- USD; 0 for local/stub
    latency_ms        INTEGER,
    ok                INTEGER NOT NULL DEFAULT 1,    -- 0 if the call errored
    error             TEXT,
    prompt_name       TEXT,                          -- which versioned Prompt produced this
    prompt_version    INTEGER,
    created_at        TEXT NOT NULL                  -- ISO8601 UTC
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_task ON llm_calls(task);

-- Inbound emails: triage, LLM extraction, and link to jobs/applications.
CREATE TABLE IF NOT EXISTS email_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mailbox         TEXT NOT NULL,
    uid             INTEGER NOT NULL,
    message_id      TEXT,
    thread_id       TEXT,
    from_addr       TEXT,
    from_name       TEXT,
    subject         TEXT,
    received_at     TEXT,
    snippet         TEXT,
    body_text       TEXT,
    category        TEXT CHECK (category IS NULL OR category IN ({sql_in_list(EmailCategory)})),
    extracted       TEXT,
    company_id      INTEGER REFERENCES companies(id),
    job_id          INTEGER REFERENCES jobs(id),
    application_id  INTEGER REFERENCES applications(id),
    action_state    TEXT NOT NULL DEFAULT '{EmailActionState.NONE}'
                        CHECK (action_state IN ({sql_in_list(EmailActionState)})),
    structured_at   TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(message_id),
    UNIQUE(mailbox, uid)
);
CREATE INDEX IF NOT EXISTS idx_email_messages_category     ON email_messages(category);
CREATE INDEX IF NOT EXISTS idx_email_messages_action_state ON email_messages(action_state);

-- Per-mailbox IMAP sync cursor (uidvalidity + highest seen uid).
CREATE TABLE IF NOT EXISTS email_sync_state (
    mailbox     TEXT PRIMARY KEY,
    uidvalidity INTEGER,
    last_uid    INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL
);

-- Proposed/confirmed/executed actions on individual email messages.
CREATE TABLE IF NOT EXISTS email_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id    INTEGER NOT NULL REFERENCES email_messages(id),
    kind        TEXT NOT NULL CHECK (kind IN ({sql_in_list(EmailActionKind)})),
    payload     TEXT,
    state       TEXT NOT NULL DEFAULT '{EmailActionState.PROPOSED}'
                    CHECK (state IN ({sql_in_list(EmailActionState)})),
    created_at  TEXT NOT NULL,
    executed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_email_actions_email_id ON email_actions(email_id);
"""


def now_iso() -> str:
    """UTC ISO-8601 timestamp — used for all `*_at` columns."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def describe() -> str:
    return f"sqlite:{DB_PATH}"


def raw_select(sql: str) -> list[dict[str, Any]]:
    """ADMIN escape hatch — an ad-hoc READ-ONLY query that bypasses the repo layer.

    Guarded to SELECT/WITH so it can never mutate. Used by analytics (fixed queries)
    and the `hunt db` inspection command; not for application code paths.
    """
    if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
        raise ValueError("raw_select is read-only — SELECT/WITH statements only")
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def init_db(path: Path | None = None) -> None:
    """Apply additive migrations, then (idempotently) create any missing schema.

    Migrations run FIRST so columns added to pre-existing tables (e.g. `jobs.state`)
    exist before `SCHEMA` creates indexes that reference them. On a fresh DB the
    migrations are no-ops (tables don't exist yet) and `SCHEMA` creates everything.
    """
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        _migrate(conn)
        conn.executescript(SCHEMA)


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive, idempotent column migrations for DBs created before a column existed.

    `CREATE TABLE IF NOT EXISTS` never alters an existing table, so a DB created by
    an earlier version is patched here. (CHECK constraints only bind on fresh tables;
    the app enforces enum values on migrated DBs.)
    """
    _ensure_column(conn, "scores", "confidence", "INTEGER")
    _ensure_column(conn, "scores", "scored_against", "TEXT")
    _ensure_column(conn, "scores", "input_hash", "TEXT")
    _ensure_column(conn, "scores", "provider_model", "TEXT")
    _ensure_column(conn, "jobs", "description_full", "TEXT")
    _ensure_column(conn, "jobs", "enriched_at", "TEXT")
    _ensure_column(
        conn, "applications", "stage",
        f"TEXT NOT NULL DEFAULT '{ApplicationStage.APPLIED}'",
    )
    _ensure_column(conn, "jobs", "state", f"TEXT NOT NULL DEFAULT '{JobState.DISCOVERED}'")
    _ensure_column(conn, "runs", "status", f"TEXT NOT NULL DEFAULT '{RunStatus.QUEUED}'")
    _ensure_column(conn, "runs", "heartbeat_at", "TEXT")
    _ensure_column(conn, "runs", "cancel_requested", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "runs", "log", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "events", "retry_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "events", "dead_at", "TEXT")
    _ensure_column(conn, "llm_calls", "prompt_name", "TEXT")
    _ensure_column(conn, "llm_calls", "prompt_version", "INTEGER")


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if cols and col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context-managed SQLite connection with row factory + FK enforcement.

    `path` resolves to the module-level ``DB_PATH`` at call time when omitted,
    so tests can redirect storage by monkeypatching ``db.DB_PATH``.
    """
    path = path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _to_json(value: Any) -> str:
    """Serialize a value for storage in a TEXT column."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def upsert_resume_variant(
    *,
    slug: str,
    source_path: str,
    parsed: dict[str, Any],
    tags: list[str],
) -> int:
    """Insert-or-update a resume variant. Returns its row id."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO resume_variants (slug, source_path, parsed_json, tags, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
              source_path = excluded.source_path,
              parsed_json = excluded.parsed_json,
              tags        = excluded.tags,
              updated_at  = excluded.updated_at
            """,
            (slug, source_path, _to_json(parsed), _to_json(tags), now_iso()),
        )
        row = conn.execute(
            "SELECT id FROM resume_variants WHERE slug = ?", (slug,)
        ).fetchone()
        return int(row["id"])


def insert_job_if_new(
    *,
    dedup_hash: str,
    source: str,
    source_job_id: str | None,
    title: str,
    company: str,
    location: str | None,
    description: str | None,
    apply_url: str,
    posted_date: str | None,
    raw_payload: dict[str, Any] | None = None,
    emit_discovered: bool = False,
) -> int | None:
    """Insert a job. Returns its id on insert, or None if it was already there.

    With `emit_discovered=True`, the row + its DISCOVERED audit row + the JOB_DISCOVERED
    event are written in ONE transaction, so a freshly-created job can never exist without
    its discovery event (which would orphan it out of the pipeline).
    """
    ts = now_iso()
    with connect() as conn:
        # ON CONFLICT(dedup_hash) DO NOTHING absorbs ONLY the dedup collision (returns None);
        # any other integrity violation (NOT NULL/CHECK/FK) still raises — matching Postgres,
        # instead of the old blanket except that hid malformed rows as "duplicate".
        cur = conn.execute(
            """
            INSERT INTO jobs (
                dedup_hash, source, source_job_id, title, company, location,
                description, apply_url, posted_date, discovered_at, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedup_hash) DO NOTHING
            """,
            (
                dedup_hash, source, source_job_id, title, company, location,
                description, apply_url, posted_date, ts,
                _to_json(raw_payload) if raw_payload is not None else None,
            ),
        )
        if cur.rowcount == 0:  # dedup collision — nothing inserted
            return None
        job_id = int(cur.lastrowid)
        if emit_discovered:
            conn.execute(
                "INSERT INTO job_transitions (job_id, from_state, to_state, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (job_id, None, str(JobState.DISCOVERED), "scrape", ts),
            )
            conn.execute(
                "INSERT INTO events (type, class, payload, created_at) VALUES (?, ?, ?, ?)",
                (str(EventType.JOB_DISCOVERED), str(EventClass.DOMAIN),
                 _to_json({"job_id": job_id}), ts),
            )
        return job_id


def list_resume_variants() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM resume_variants ORDER BY slug"
        ).fetchall()


def list_board_jobs(limit: int = 200) -> list[dict[str, Any]]:
    """Jobs for the Kanban: each with its state + best score (unscored jobs sort last)."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT j.id, j.title, j.company, j.location, j.state, j.apply_url, "
            "MAX(s.fit_score) AS best_score "
            "FROM jobs j LEFT JOIN scores s ON s.job_id = j.id "
            "GROUP BY j.id ORDER BY (MAX(s.fit_score) IS NULL), MAX(s.fit_score) DESC LIMIT ?",
            (limit,)).fetchall()]


def write_score(
    *,
    job_id: int,
    variant_id: int,
    fit_score: int,
    reasoning: str,
    confidence: int | None = None,
    scored_against: str | None = None,
    input_hash: str | None = None,
    provider_model: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO scores (job_id, variant_id, fit_score, confidence, reasoning,
                                scored_against, input_hash, provider_model, scored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, variant_id) DO UPDATE SET
              fit_score      = excluded.fit_score,
              confidence     = excluded.confidence,
              reasoning      = excluded.reasoning,
              scored_against = excluded.scored_against,
              input_hash     = excluded.input_hash,
              provider_model = excluded.provider_model,
              scored_at      = excluded.scored_at
            """,
            (job_id, variant_id, fit_score, confidence, reasoning,
             scored_against, input_hash, provider_model, now_iso()),
        )


def list_scorable_jobs(limit: int = 200) -> list[sqlite3.Row]:
    """Jobs eligible for (re)scoring — not yet in a terminal/applied state."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT id, title, company, location, source, description, description_full, state
            FROM jobs
            WHERE state IN ('discovered', 'enriched', 'scored')
            ORDER BY discovered_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def scores_meta_for_job(job_id: int) -> list[sqlite3.Row]:
    """(variant_id, input_hash, provider_model) per existing score — for idempotency."""
    with connect() as conn:
        return conn.execute(
            "SELECT variant_id, input_hash, provider_model FROM scores WHERE job_id = ?",
            (job_id,),
        ).fetchall()


def scores_meta_for_jobs(job_ids: list[int]) -> dict[int, list[sqlite3.Row]]:
    """Batched `scores_meta_for_job` for many jobs in ONE query (avoids the scoring N+1)."""
    if not job_ids:
        return {}
    placeholders = ",".join("?" * len(job_ids))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT job_id, variant_id, input_hash, provider_model FROM scores "
            f"WHERE job_id IN ({placeholders})",
            [int(j) for j in job_ids],
        ).fetchall()
    out: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        out.setdefault(int(row["job_id"]), []).append(row)
    return out


def set_job_enriched(job_id: int, description_full: str) -> None:
    """Store the full JD text + enriched timestamp."""
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET description_full = ?, enriched_at = ? WHERE id = ?",
            (description_full, now_iso(), int(job_id)),
        )


# ---------- drafting (tailored resumes + cover letters/outreach) ----------


def best_scored_variant(job_id: int) -> sqlite3.Row | None:
    """The highest-scoring variant (id, slug, source_path, parsed_json) for a job, or None."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT rv.id, rv.slug, rv.source_path, rv.parsed_json
            FROM scores s JOIN resume_variants rv ON rv.id = s.variant_id
            WHERE s.job_id = ? ORDER BY s.fit_score DESC, rv.id ASC LIMIT 1
            """,
            (job_id,),
        ).fetchone()


def save_tailored_resume(*, job_id: int, variant_id: int, content: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tailored_resumes (job_id, variant_id, content, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(job_id, variant_id) DO UPDATE SET
              content = excluded.content, created_at = excluded.created_at
            """,
            (int(job_id), int(variant_id), content, now_iso()),
        )


def get_tailored_resume(job_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM tailored_resumes WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (int(job_id),),
        ).fetchone()


def save_draft(*, job_id: int, kind: str, body: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO drafts (job_id, kind, body, created_at) VALUES (?, ?, ?, ?)",
            (int(job_id), str(kind), body, now_iso()),
        )
        return int(cur.lastrowid)


def list_drafts_for_job(job_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM drafts WHERE job_id = ? ORDER BY id DESC", (int(job_id),)
        ).fetchall()


def get_company(name: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM companies WHERE name = ?", (name,)).fetchone()


def company_history(company: str) -> list[sqlite3.Row]:
    """Every role at a company + its application stage — 'have I engaged here before?'."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT j.id, j.title, j.state, j.discovered_at, a.stage, a.applied_at
            FROM jobs j LEFT JOIN applications a ON a.job_id = j.id
            WHERE j.company = ? ORDER BY j.discovered_at DESC
            """,
            (company,),
        ).fetchall()


def save_contact(
    *, company: str, name: str, role: str | None = None, persona: str | None = None,
    email_guess: str | None = None, linkedin_url: str | None = None, notes: str | None = None,
) -> int:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO contacts (company, name, role, persona, email_guess, linkedin_url, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company, name) DO UPDATE SET
              role = excluded.role, persona = excluded.persona,
              email_guess = excluded.email_guess, linkedin_url = excluded.linkedin_url,
              notes = excluded.notes
            """,
            (company, name, role, persona, email_guess, linkedin_url, notes, now_iso()),
        )
        row = conn.execute(
            "SELECT id FROM contacts WHERE company = ? AND name = ?", (company, name)
        ).fetchone()
        return int(row["id"])


def list_contacts(company: str | None = None) -> list[sqlite3.Row]:
    with connect() as conn:
        if company:
            return conn.execute(
                "SELECT * FROM contacts WHERE company = ? ORDER BY name", (company,)
            ).fetchall()
        return conn.execute("SELECT * FROM contacts ORDER BY company, name").fetchall()


def save_answer_template(
    *, question_pattern: str, answer_text: str, tags: list[str] | None = None
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO answer_templates (question_pattern, answer_text, tags, created_at) "
            "VALUES (?, ?, ?, ?)",
            (question_pattern, answer_text,
             _to_json(tags) if tags is not None else None, now_iso()),
        )
        return int(cur.lastrowid)


def list_answer_templates() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM answer_templates ORDER BY id DESC"
        ).fetchall()


def set_user_context(*, content: str, fmt: str) -> None:
    """Store (or replace) the single user career-context blob."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO user_context (id, content, format, updated_at) VALUES (1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET content = excluded.content, "
            "format = excluded.format, updated_at = excluded.updated_at",
            (content, str(fmt), now_iso()),
        )


def get_user_context() -> sqlite3.Row | None:
    """Return the single user-context row, or None if unset."""
    with connect() as conn:
        return conn.execute("SELECT * FROM user_context WHERE id = 1").fetchone()


def set_search_prefs(*, content: str) -> None:
    """Store (or replace) the user's job-search preferences blob."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO search_prefs (id, content, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET content = excluded.content, "
            "updated_at = excluded.updated_at",
            (content, now_iso()),
        )


def get_search_prefs() -> sqlite3.Row | None:
    """Return the single search-prefs row, or None if unset."""
    with connect() as conn:
        return conn.execute("SELECT * FROM search_prefs WHERE id = 1").fetchone()


_APPLICANT_COLS = (
    "first_name", "last_name", "email", "phone", "location", "linkedin_url",
    "github_url", "portfolio_url", "work_authorization", "needs_sponsorship",
    "willing_to_relocate", "notice_period", "expected_ctc", "current_ctc",
    "years_experience", "referral_source", "extra",
)


def set_applicant_profile(*, fields: dict[str, Any]) -> None:
    """Upsert the single applicant-profile row (only known columns are written)."""
    cols = [c for c in _APPLICANT_COLS if c in fields]
    assignments = ", ".join(f"{c} = excluded.{c}" for c in cols)
    placeholders = ", ".join("?" for _ in cols)
    values = [_to_json(fields[c]) if c == "extra" else fields[c] for c in cols]
    with connect() as conn:
        conn.execute(
            f"INSERT INTO applicant_profile (id, {', '.join(cols)}, updated_at) "
            f"VALUES (1, {placeholders}, ?) "
            f"ON CONFLICT(id) DO UPDATE SET {assignments}, updated_at = excluded.updated_at",
            (*values, now_iso()),
        )


def get_applicant_profile() -> sqlite3.Row | None:
    """Return the single applicant-profile row, or None if unset."""
    with connect() as conn:
        return conn.execute("SELECT * FROM applicant_profile WHERE id = 1").fetchone()


def save_learning(
    *, job_id: int, variant_id: int | None, kind: str, payload: dict[str, Any]
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO learnings (job_id, variant_id, kind, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (int(job_id), variant_id, str(kind), _to_json(payload), now_iso()),
        )
        return int(cur.lastrowid)


def list_learnings_for_job(job_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM learnings WHERE job_id = ? ORDER BY id DESC", (int(job_id),)
        ).fetchall()


# ---------- embeddings (Postgres/pgvector only) ----------

_SEMANTIC_MSG = "semantic search requires the Postgres backend (DB_BACKEND=postgres)"


def set_job_embedding(job_id: int, embedding: list[float]) -> None:
    raise NotImplementedError(_SEMANTIC_MSG)


def set_variant_embedding(variant_id: int, embedding: list[float]) -> None:
    raise NotImplementedError(_SEMANTIC_MSG)


def jobs_missing_embedding(limit: int = 200) -> list[sqlite3.Row]:
    raise NotImplementedError(_SEMANTIC_MSG)


def semantic_jobs(embedding: list[float], limit: int = 10) -> list[sqlite3.Row]:
    raise NotImplementedError(_SEMANTIC_MSG)


def write_llm_call(
    *,
    task: str,
    provider: str,
    model: str,
    prompt: str | None,
    response: str | None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost: float | None = None,
    latency_ms: int | None = None,
    ok: bool = True,
    error: str | None = None,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
) -> None:
    """Best-effort observability log of one LLM call. Never raises."""
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (
                    task, provider, model, prompt, response, prompt_tokens,
                    completion_tokens, cost, latency_ms, ok, error,
                    prompt_name, prompt_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task, provider, model, prompt, response, prompt_tokens,
                    completion_tokens, cost, latency_ms, 1 if ok else 0, error,
                    prompt_name, prompt_version, now_iso(),
                ),
            )
    except Exception:  # noqa: BLE001 — logging must never break a chat call
        pass


def top_matches(min_score: int = 70, limit: int = 10) -> list[sqlite3.Row]:
    """Best-scoring jobs — ONE row per job with its actual winning (max-score) variant."""
    with connect() as conn:
        return conn.execute(
            f"""
            SELECT
                j.id            AS job_id,
                j.title         AS title,
                j.company       AS company,
                j.location      AS location,
                j.apply_url     AS apply_url,
                j.source        AS source,
                s.fit_score     AS best_score,
                rv.slug         AS best_variant
            FROM jobs j
            JOIN scores s ON s.job_id = j.id
                        AND s.variant_id = (
                            SELECT variant_id FROM scores WHERE job_id = j.id
                            ORDER BY fit_score DESC, variant_id ASC LIMIT 1
                        )
            JOIN resume_variants rv ON rv.id = s.variant_id
            WHERE j.state NOT IN ({sql_values(CLOSED_STATES)})
              AND s.fit_score >= ?
            ORDER BY best_score DESC, j.discovered_at DESC
            LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()


# ---------- Read/write helpers used by the services layer (keep SQL out of services) ----------


def get_job(job_id: int) -> sqlite3.Row | None:
    """Fetch one job row by id, or None."""
    with connect() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def list_scores_for_job(job_id: int) -> list[sqlite3.Row]:
    """All variant scores for a job, best first, with the variant slug joined in."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT rv.slug AS variant, s.fit_score, s.confidence, s.reasoning, s.scored_at
            FROM scores s
            JOIN resume_variants rv ON rv.id = s.variant_id
            WHERE s.job_id = ?
            ORDER BY s.fit_score DESC
            """,
            (job_id,),
        ).fetchall()


def find_variant_id_by_slug(slug: str) -> int | None:
    """Resolve a resume-variant slug to its id, or None if unknown."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM resume_variants WHERE slug = ?", (slug,)
        ).fetchone()
        return int(row["id"]) if row else None


def set_application_stage(job_id: int, stage: Any) -> None:
    """Advance an application's interview-pipeline stage."""
    with connect() as conn:
        conn.execute(
            "UPDATE applications SET stage = ? WHERE job_id = ?", (str(stage), int(job_id))
        )


def record_application(*, job_id: int, variant_id: int, cover_letter: str) -> None:
    """Upsert an application row (one per job)."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO applications (job_id, variant_id, cover_letter, applied_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET
                variant_id   = excluded.variant_id,
                cover_letter = excluded.cover_letter,
                applied_at   = excluded.applied_at
            """,
            (int(job_id), int(variant_id), cover_letter),
        )


# ---------- state machine ----------


def get_job_state(job_id: int) -> str:
    with connect() as conn:
        row = conn.execute("SELECT state FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"no job with id={job_id}")
    return row["state"]


def set_job_state(job_id: int, state: Any) -> None:
    with connect() as conn:
        conn.execute("UPDATE jobs SET state = ? WHERE id = ?", (str(state), int(job_id)))


def write_job_transition(
    *, job_id: int, from_state: str | None, to_state: str, reason: str | None = None
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO job_transitions (job_id, from_state, to_state, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (int(job_id), from_state, to_state, reason, now_iso()),
        )


def apply_transition(
    *, job_id: int, from_state: str | None, to_state: str, reason: str | None = None,
    event_type: str | None = None, event_class: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Audit + state change + (optional) event append — in ONE transaction (the outbox invariant)."""
    ts = now_iso()
    with connect() as conn:  # single connect() == single transaction (commit on clean exit)
        conn.execute(
            "INSERT INTO job_transitions (job_id, from_state, to_state, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (int(job_id), from_state, to_state, reason, ts),
        )
        conn.execute("UPDATE jobs SET state = ? WHERE id = ?", (to_state, int(job_id)))
        if event_type is not None:
            conn.execute(
                "INSERT INTO events (type, class, payload, created_at) VALUES (?, ?, ?, ?)",
                (event_type, event_class,
                 _to_json(payload) if payload is not None else None, ts),
            )


# ---------- event outbox ----------


def write_event(*, type: str, cls: str, payload: dict[str, Any] | None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (type, class, payload, created_at) VALUES (?, ?, ?, ?)",
            (type, cls, _to_json(payload) if payload is not None else None, now_iso()),
        )


def fetch_unprocessed_events(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, type, class, payload, created_at, retry_count FROM events "
                "WHERE processed_at IS NULL AND dead_at IS NULL ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        ]


def mark_event_processed(event_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE events SET processed_at = ? WHERE id = ?", (now_iso(), int(event_id))
        )


def record_event_failure(event_id: int, *, max_retries: int) -> str:
    """Increment retry_count; dead-letter once it reaches max_retries. Returns 'retry'|'dead'."""
    with connect() as conn:
        conn.execute(
            "UPDATE events SET retry_count = retry_count + 1 WHERE id = ?", (int(event_id),)
        )
        count = conn.execute(
            "SELECT retry_count FROM events WHERE id = ?", (int(event_id),)
        ).fetchone()["retry_count"]
        if count >= max_retries:
            conn.execute(
                "UPDATE events SET dead_at = ? WHERE id = ?", (now_iso(), int(event_id))
            )
            return "dead"
        return "retry"


# ---------- runs ----------


def create_run(sources: list[str]) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (started_at, sources, status, heartbeat_at) VALUES (?, ?, ?, ?)",
            (now_iso(), _to_json(sources), str(RunStatus.QUEUED), now_iso()),
        )
        return int(cur.lastrowid)


def start_run(run_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, started_at = ?, heartbeat_at = ? WHERE id = ?",
            (str(RunStatus.RUNNING), now_iso(), now_iso(), int(run_id)),
        )


def heartbeat_run(run_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET heartbeat_at = ? WHERE id = ?", (now_iso(), int(run_id))
        )


def finish_run(
    run_id: int, status: Any, *, jobs_found: int = 0, jobs_new: int = 0,
    errors: Any = None,
) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, jobs_found = ?, jobs_new = ?, "
            "errors = ? WHERE id = ?",
            (str(status), now_iso(), jobs_found, jobs_new,
             _to_json(errors) if errors is not None else None, int(run_id)),
        )


def request_run_cancel(run_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE runs SET cancel_requested = 1 WHERE id = ?", (int(run_id),))


def run_cancel_requested(run_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT cancel_requested FROM runs WHERE id = ?", (int(run_id),)
        ).fetchone()
    return bool(row["cancel_requested"]) if row else False


def append_run_log(run_id: int, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET log = log || ? WHERE id = ?",
            (f"{now_iso()} {message}\n", int(run_id)),
        )


def get_run(run_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (int(run_id),)).fetchone()
    return dict(row) if row else None


def list_recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def count_runs_today() -> int:
    """Discovery runs started today (drives the per-day cap)."""
    with connect() as conn:
        return conn.execute(
            "SELECT count(*) AS c FROM runs WHERE substr(started_at, 1, 10) = ?",
            (now_iso()[:10],),
        ).fetchone()["c"]


def reap_stale_runs(max_age_s: int = 3600) -> int:
    """Mark 'running' runs whose heartbeat is older than max_age_s as failed (crash recovery).
    Returns the number reaped."""
    now_utc = datetime.now(UTC)
    cutoff = (now_utc - timedelta(seconds=max_age_s)).isoformat(timespec="seconds")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE runs SET status = ?, finished_at = ? "
            "WHERE status = ? AND (heartbeat_at IS NULL OR heartbeat_at < ?)",
            (str(RunStatus.FAILED), now_iso(), str(RunStatus.RUNNING), cutoff),
        )
        return cur.rowcount


# ---------- search profiles ----------


def create_search_profile(
    *, name: str, keywords: str, location: str, pages: int = 1,
    exclusions: list[str] | None = None, min_salary: int | None = None,
    companies_include: list[str] | None = None, companies_exclude: list[str] | None = None,
    remote_only: bool = False, min_yoe: int | None = None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO search_profiles (name, keywords, location, pages, exclusions, "
            "min_salary, companies_include, companies_exclude, remote_only, min_yoe, "
            "enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (name, keywords, location, pages,
             _to_json(exclusions) if exclusions is not None else None, min_salary,
             _to_json(companies_include) if companies_include is not None else None,
             _to_json(companies_exclude) if companies_exclude is not None else None,
             1 if remote_only else 0, min_yoe, now_iso()),
        )
        return int(cur.lastrowid)


def list_search_profiles() -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM search_profiles ORDER BY name").fetchall()]


def list_active_search_profiles() -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM search_profiles WHERE enabled = 1 ORDER BY name").fetchall()]


def get_search_profile(profile_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM search_profiles WHERE id = ?", (int(profile_id),)
        ).fetchone()
    return dict(row) if row else None


def set_search_profile_enabled(profile_id: int, enabled: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE search_profiles SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, int(profile_id)),
        )


# ---------- email triage ----------


def upsert_email_message(
    *,
    mailbox: str,
    uid: int,
    message_id: str | None,
    thread_id: str | None,
    from_addr: str | None,
    from_name: str | None,
    subject: str | None,
    received_at: str | None,
    snippet: str | None,
    body_text: str | None,
) -> int:
    """Insert an email (dedup by message_id or mailbox+uid). Return the row id."""
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO email_messages (
                mailbox, uid, message_id, thread_id, from_addr, from_name,
                subject, received_at, snippet, body_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mailbox, uid, message_id, thread_id, from_addr, from_name,
             subject, received_at, snippet, body_text, now_iso()),
        )
        # INSERT OR IGNORE returns no row on conflict — SELECT to get the id.
        if message_id is not None:
            row = conn.execute(
                "SELECT id FROM email_messages WHERE message_id = ?", (message_id,)
            ).fetchone()
            if row is None:  # edge case: conflict was on (mailbox, uid) with different message_id
                row = conn.execute(
                    "SELECT id FROM email_messages WHERE mailbox = ? AND uid = ?",
                    (mailbox, uid),
                ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM email_messages WHERE mailbox = ? AND uid = ?",
                (mailbox, uid),
            ).fetchone()
        return int(row["id"])


def set_email_structured(
    email_id: int,
    *,
    category: str | None,
    extracted: dict[str, Any],
    structured_at: str,
) -> None:
    """Store LLM extraction results on an email message."""
    with connect() as conn:
        conn.execute(
            "UPDATE email_messages SET category = ?, extracted = ?, structured_at = ? "
            "WHERE id = ?",
            (category, _to_json(extracted), structured_at, int(email_id)),
        )


def set_email_links(
    email_id: int,
    *,
    company_id: int | None,
    job_id: int | None,
    application_id: int | None,
) -> None:
    """Set the FK links from an email to company/job/application rows."""
    with connect() as conn:
        conn.execute(
            "UPDATE email_messages SET company_id = ?, job_id = ?, application_id = ? "
            "WHERE id = ?",
            (company_id, job_id, application_id, int(email_id)),
        )


def set_email_action_state(email_id: int, state: str) -> None:
    """Advance the action lifecycle state of an email."""
    with connect() as conn:
        conn.execute(
            "UPDATE email_messages SET action_state = ? WHERE id = ?",
            (state, int(email_id)),
        )


def get_email_message(email_id: int) -> sqlite3.Row | None:
    """Return one email_messages row by id, or None."""
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM email_messages WHERE id = ?", (int(email_id),)
        ).fetchone()


def list_email_messages(
    *,
    category: str | None = None,
    action_state: str | None = None,
    limit: int = 100,
) -> list[sqlite3.Row]:
    """Return email messages filtered by optional category and/or action_state."""
    conditions: list[str] = []
    params: list[Any] = []
    if category is not None:
        conditions.append("category = ?")
        params.append(category)
    if action_state is not None:
        conditions.append("action_state = ?")
        params.append(action_state)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with connect() as conn:
        return conn.execute(
            f"SELECT * FROM email_messages {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()


def list_unstructured_emails(limit: int = 50) -> list[sqlite3.Row]:
    """Return emails that have not been LLM-structured yet (category IS NULL)."""
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM email_messages WHERE category IS NULL ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()


def get_sync_state(mailbox: str) -> sqlite3.Row | None:
    """Return the sync cursor row for a mailbox, or None if never synced."""
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM email_sync_state WHERE mailbox = ?", (mailbox,)
        ).fetchone()


def set_sync_state(*, mailbox: str, uidvalidity: int | None, last_uid: int) -> None:
    """Upsert the IMAP sync cursor for a mailbox."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO email_sync_state (mailbox, uidvalidity, last_uid, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(mailbox) DO UPDATE SET
              uidvalidity = excluded.uidvalidity,
              last_uid    = excluded.last_uid,
              updated_at  = excluded.updated_at
            """,
            (mailbox, uidvalidity, last_uid, now_iso()),
        )


def get_application_by_job(job_id: int) -> sqlite3.Row | None:
    """Return the application row (id, stage) for a job, or None if not applied."""
    with connect() as conn:
        return conn.execute(
            "SELECT id, stage FROM applications WHERE job_id = ?", (int(job_id),)
        ).fetchone()


# ---------- email actions ----------


def create_email_action(
    *,
    email_id: int,
    kind: str,
    payload: dict[str, Any],
) -> int:
    """Insert a new email action row in the 'proposed' state. Return its id."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO email_actions (email_id, kind, payload, state, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                int(email_id),
                kind,
                _to_json(payload),
                str(EmailActionState.PROPOSED),
                now_iso(),
            ),
        )
        return int(cur.lastrowid)


def get_email_action(action_id: int) -> sqlite3.Row | None:
    """Return one email_actions row by id, or None."""
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM email_actions WHERE id = ?", (int(action_id),)
        ).fetchone()


def get_latest_action_for_email(email_id: int) -> sqlite3.Row | None:
    """Return the most recent email_actions row for email_id (highest id), or None."""
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM email_actions WHERE email_id = ? ORDER BY id DESC LIMIT 1",
            (int(email_id),),
        ).fetchone()


def set_email_action_result(
    action_id: int,
    *,
    state: str,
    executed_at: str,
) -> None:
    """Update the state and executed_at timestamp of an email action."""
    with connect() as conn:
        conn.execute(
            "UPDATE email_actions SET state = ?, executed_at = ? WHERE id = ?",
            (state, executed_at, int(action_id)),
        )
