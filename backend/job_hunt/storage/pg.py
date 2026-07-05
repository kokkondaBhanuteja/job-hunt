"""Postgres repository (psycopg3) — the production datastore.

Mirrors the function surface of `storage/db.py` (the SQLite test backend) so the
`storage.repo` façade can swap between them with zero changes at call sites.

Compatibility note: JSON/timestamp columns are returned **as text** (`::text`) so
downstream code that does `json.loads(parsed_json)` or treats `*_at` as ISO strings
behaves identically to the SQLite backend.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from job_hunt.enums import (
    CLOSED_STATES,
    EmailActionState,
    EventClass,
    EventType,
    JobState,
    RunStatus,
    sql_values,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://jobhunt:jobhunt@localhost:55432/jobhunt"
)
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def describe() -> str:
    return f"postgres:{DATABASE_URL}"


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Apply any unapplied numbered migrations from migrations/*.sql. Idempotent."""
    with connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {
            r["filename"]
            for r in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
            )


# ---------- writes ----------


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
    """Insert a job; return its id, or None if the dedup_hash already existed.

    With `emit_discovered=True`, the row + DISCOVERED audit row + JOB_DISCOVERED event are
    written in ONE transaction so a new job can never exist without its discovery event.
    """
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO jobs (
                dedup_hash, source, source_job_id, title, company, location,
                description, apply_url, posted_date, raw_payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dedup_hash) DO NOTHING
            RETURNING id
            """,
            (
                dedup_hash, source, source_job_id, title, company, location,
                description, apply_url, posted_date,
                Jsonb(raw_payload) if raw_payload is not None else None,
            ),
        ).fetchone()
        if row is None:
            return None
        job_id = int(row["id"])
        if emit_discovered:
            conn.execute(
                "INSERT INTO job_transitions (job_id, from_state, to_state, reason) "
                "VALUES (%s, %s, %s, %s)",
                (job_id, None, str(JobState.DISCOVERED), "scrape"),
            )
            conn.execute(
                "INSERT INTO events (type, class, payload) VALUES (%s, %s, %s)",
                (str(EventType.JOB_DISCOVERED), str(EventClass.DOMAIN),
                 Jsonb({"job_id": job_id})),
            )
        return job_id


def upsert_resume_variant(
    *, slug: str, source_path: str, parsed: dict[str, Any], tags: list[str]
) -> int:
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO resume_variants (slug, source_path, parsed_json, tags, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (slug) DO UPDATE SET
              source_path = EXCLUDED.source_path,
              parsed_json = EXCLUDED.parsed_json,
              tags        = EXCLUDED.tags,
              updated_at  = EXCLUDED.updated_at
            RETURNING id
            """,
            (slug, source_path, Jsonb(parsed), Jsonb(tags)),
        ).fetchone()
        return int(row["id"])


def write_score(
    *, job_id: int, variant_id: int, fit_score: int, reasoning: str,
    confidence: int | None = None, scored_against: str | None = None,
    input_hash: str | None = None, provider_model: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO scores (job_id, variant_id, fit_score, confidence, reasoning,
                                scored_against, input_hash, provider_model, scored_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (job_id, variant_id) DO UPDATE SET
              fit_score      = EXCLUDED.fit_score,
              confidence     = EXCLUDED.confidence,
              reasoning      = EXCLUDED.reasoning,
              scored_against = EXCLUDED.scored_against,
              input_hash     = EXCLUDED.input_hash,
              provider_model = EXCLUDED.provider_model,
              scored_at      = EXCLUDED.scored_at
            """,
            (job_id, variant_id, fit_score, confidence, reasoning,
             scored_against, input_hash, provider_model),
        )


def list_scorable_jobs(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT id, title, company, location, source, description, description_full, state
            FROM jobs
            WHERE state IN ('discovered', 'enriched', 'scored')
            ORDER BY discovered_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


def scores_meta_for_job(job_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT variant_id, input_hash, provider_model FROM scores WHERE job_id = %s",
            (job_id,),
        ).fetchall()


def scores_meta_for_jobs(job_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Batched `scores_meta_for_job` for many jobs in ONE query (avoids the scoring N+1)."""
    if not job_ids:
        return {}
    with connect() as conn:
        rows = conn.execute(
            "SELECT job_id, variant_id, input_hash, provider_model FROM scores "
            "WHERE job_id = ANY(%s)",
            ([int(j) for j in job_ids],),
        ).fetchall()
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(int(row["job_id"]), []).append(row)
    return out


def set_job_enriched(job_id: int, description_full: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET description_full = %s, enriched_at = now() WHERE id = %s",
            (description_full, int(job_id)),
        )


# ---------- drafting ----------


def best_scored_variant(job_id: int) -> dict[str, Any] | None:
    """The highest-scoring variant (id, slug, source_path, parsed_json) for a job, or None."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT rv.id, rv.slug, rv.source_path, rv.parsed_json::text AS parsed_json
            FROM scores s JOIN resume_variants rv ON rv.id = s.variant_id
            WHERE s.job_id = %s ORDER BY s.fit_score DESC, rv.id ASC LIMIT 1
            """,
            (job_id,),
        ).fetchone()


def save_tailored_resume(*, job_id: int, variant_id: int, content: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tailored_resumes (job_id, variant_id, content)
            VALUES (%s, %s, %s)
            ON CONFLICT (job_id, variant_id) DO UPDATE SET
              content = EXCLUDED.content, created_at = now()
            """,
            (int(job_id), int(variant_id), content),
        )


def get_tailored_resume(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return conn.execute(
            "SELECT id, job_id, variant_id, content, created_at::text AS created_at "
            "FROM tailored_resumes WHERE job_id = %s ORDER BY id DESC LIMIT 1",
            (int(job_id),),
        ).fetchone()


def save_draft(*, job_id: int, kind: str, body: str) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO drafts (job_id, kind, body) VALUES (%s, %s, %s) RETURNING id",
            (int(job_id), str(kind), body),
        ).fetchone()["id"]


def list_drafts_for_job(job_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, job_id, kind, body, status, created_at::text AS created_at "
            "FROM drafts WHERE job_id = %s ORDER BY id DESC",
            (int(job_id),),
        ).fetchall()


def get_company(name: str) -> dict[str, Any] | None:
    with connect() as conn:
        return conn.execute(
            "SELECT id, name, size, funding_stage, tech::text AS tech, glassdoor, notes, "
            "fetched_at::text AS fetched_at FROM companies WHERE name = %s",
            (name,),
        ).fetchone()


def company_history(company: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT j.id, j.title, j.state, j.discovered_at::text AS discovered_at,
                   a.stage, a.applied_at::text AS applied_at
            FROM jobs j LEFT JOIN applications a ON a.job_id = j.id
            WHERE j.company = %s ORDER BY j.discovered_at DESC
            """,
            (company,),
        ).fetchall()


def save_contact(
    *, company: str, name: str, role: str | None = None, persona: str | None = None,
    email_guess: str | None = None, linkedin_url: str | None = None, notes: str | None = None,
) -> int:
    with connect() as conn:
        return conn.execute(
            """
            INSERT INTO contacts (company, name, role, persona, email_guess, linkedin_url, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company, name) DO UPDATE SET
              role = EXCLUDED.role, persona = EXCLUDED.persona,
              email_guess = EXCLUDED.email_guess, linkedin_url = EXCLUDED.linkedin_url,
              notes = EXCLUDED.notes
            RETURNING id
            """,
            (company, name, role, persona, email_guess, linkedin_url, notes),
        ).fetchone()["id"]


def list_contacts(company: str | None = None) -> list[dict[str, Any]]:
    cols = ("id, company, name, role, persona, email_guess, linkedin_url, notes, "
            "created_at::text AS created_at")
    with connect() as conn:
        if company:
            return conn.execute(
                f"SELECT {cols} FROM contacts WHERE company = %s ORDER BY name", (company,)
            ).fetchall()
        return conn.execute(f"SELECT {cols} FROM contacts ORDER BY company, name").fetchall()


def save_answer_template(
    *, question_pattern: str, answer_text: str, tags: list[str] | None = None
) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO answer_templates (question_pattern, answer_text, tags) "
            "VALUES (%s, %s, %s) RETURNING id",
            (question_pattern, answer_text, Jsonb(tags) if tags is not None else None),
        ).fetchone()["id"]


def list_answer_templates() -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, question_pattern, answer_text, tags::text AS tags, "
            "created_at::text AS created_at FROM answer_templates ORDER BY id DESC"
        ).fetchall()


def set_user_context(*, content: str, fmt: str) -> None:
    """Store (or replace) the single user career-context blob."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO user_context (id, content, format, updated_at) VALUES (1, %s, %s, now()) "
            "ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, "
            "format = EXCLUDED.format, updated_at = now()",
            (content, str(fmt)),
        )


def get_user_context() -> dict[str, Any] | None:
    """Return the single user-context row, or None if unset."""
    with connect() as conn:
        return conn.execute(
            "SELECT id, content, format, updated_at::text AS updated_at "
            "FROM user_context WHERE id = 1"
        ).fetchone()


def set_search_prefs(*, content: str) -> None:
    """Store (or replace) the user's job-search preferences blob."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO search_prefs (id, content, updated_at) VALUES (1, %s, now()) "
            "ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, updated_at = now()",
            (content,),
        )


def get_search_prefs() -> dict[str, Any] | None:
    """Return the single search-prefs row, or None if unset."""
    with connect() as conn:
        return conn.execute(
            "SELECT id, content, updated_at::text AS updated_at "
            "FROM search_prefs WHERE id = 1"
        ).fetchone()


def set_apply_policy(policy: dict) -> None:
    """Store (or replace) the single apply-policy singleton."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO apply_policy (id, policy, updated_at) VALUES (1, %s, now()) "
            "ON CONFLICT (id) DO UPDATE SET policy = EXCLUDED.policy, updated_at = now()",
            (Jsonb(policy),),
        )


def get_apply_policy() -> dict[str, Any] | None:
    """Return the stored apply policy as a dict, or None if unset."""
    with connect() as conn:
        row = conn.execute("SELECT policy FROM apply_policy WHERE id = 1").fetchone()
    if row is None:
        return None
    return row["policy"]  # psycopg3 auto-deserialises JSONB → dict


_APPLICANT_COLS = (
    "first_name", "last_name", "email", "phone", "location", "linkedin_url",
    "github_url", "portfolio_url", "work_authorization", "needs_sponsorship",
    "willing_to_relocate", "notice_period", "expected_ctc", "current_ctc",
    "years_experience", "referral_source", "extra",
)


def set_applicant_profile(*, fields: dict[str, Any]) -> None:
    """Upsert the single applicant-profile row (only known columns are written)."""
    cols = [c for c in _APPLICANT_COLS if c in fields]
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    placeholders = ", ".join("%s" for _ in cols)
    values = [Jsonb(fields[c]) if c == "extra" else fields[c] for c in cols]
    with connect() as conn:
        conn.execute(
            f"INSERT INTO applicant_profile (id, {', '.join(cols)}, updated_at) "
            f"VALUES (1, {placeholders}, now()) "
            f"ON CONFLICT (id) DO UPDATE SET {assignments}, updated_at = now()",
            values,
        )


def get_applicant_profile() -> dict[str, Any] | None:
    """Return the single applicant-profile row, or None if unset."""
    with connect() as conn:
        return conn.execute(
            "SELECT *, extra::text AS extra, updated_at::text AS updated_at "
            "FROM applicant_profile WHERE id = 1"
        ).fetchone()


def save_learning(
    *, job_id: int, variant_id: int | None, kind: str, payload: dict[str, Any]
) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO learnings (job_id, variant_id, kind, payload) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (int(job_id), variant_id, str(kind), Jsonb(payload)),
        ).fetchone()["id"]


def _vec(values: list[float]) -> str:
    """pgvector text literal, e.g. '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def set_job_embedding(job_id: int, embedding: list[float]) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET embedding = %s::vector WHERE id = %s", (_vec(embedding), int(job_id))
        )


def set_variant_embedding(variant_id: int, embedding: list[float]) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE resume_variants SET embedding = %s::vector WHERE id = %s",
            (_vec(embedding), int(variant_id)),
        )


def jobs_missing_embedding(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, title, company, description, description_full FROM jobs "
            "WHERE embedding IS NULL AND (description_full IS NOT NULL OR description IS NOT NULL) "
            "LIMIT %s",
            (limit,),
        ).fetchall()


def semantic_jobs(embedding: list[float], limit: int = 10) -> list[dict[str, Any]]:
    """Nearest jobs to a query embedding by cosine distance."""
    vec = _vec(embedding)
    with connect() as conn:
        return conn.execute(
            "SELECT id, title, company, location, apply_url, "
            "(embedding <=> %s::vector) AS distance FROM jobs "
            "WHERE embedding IS NOT NULL ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, vec, limit),
        ).fetchall()


def semantic_jobs_filtered(
    job_id: int, states: list[str], limit: int = 5
) -> list[dict[str, Any]]:
    """Nearest jobs that have reached a given set of states, seeded from job_id's embedding.

    Returns an empty list if job_id has no embedding.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT embedding FROM jobs WHERE id = %s", (int(job_id),)
        ).fetchone()
    if row is None or row["embedding"] is None:
        return []
    vec = str(row["embedding"])
    with connect() as conn:
        return conn.execute(
            "SELECT id, title, company, location, apply_url, state, "
            "(embedding <=> %s::vector) AS distance FROM jobs "
            "WHERE embedding IS NOT NULL AND id != %s AND state = ANY(%s) "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, int(job_id), states, vec, int(limit)),
        ).fetchall()


def list_learnings_for_job(job_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, job_id, variant_id, kind, payload::text AS payload, "
            "created_at::text AS created_at FROM learnings WHERE job_id = %s ORDER BY id DESC",
            (int(job_id),),
        ).fetchall()


def list_learnings_by_kind(kind: str, limit: int = 500) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, job_id, kind, payload::text AS payload FROM learnings "
            "WHERE kind = %s ORDER BY id DESC LIMIT %s",
            (str(kind), limit),
        ).fetchall()


def write_llm_call(
    *, task: str, provider: str, model: str, prompt: str | None, response: str | None,
    prompt_tokens: int | None = None, completion_tokens: int | None = None,
    cost: float | None = None, latency_ms: int | None = None,
    ok: bool = True, error: str | None = None,
    prompt_name: str | None = None, prompt_version: int | None = None,
) -> None:
    """Best-effort observability log. Never raises."""
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (
                    task, provider, model, prompt, response, prompt_tokens,
                    completion_tokens, cost, latency_ms, ok, error,
                    prompt_name, prompt_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (str(task), str(provider), model, prompt, response, prompt_tokens,
                 completion_tokens, cost, latency_ms, ok, error,
                 prompt_name, prompt_version),
            )
    except Exception:  # noqa: BLE001
        pass


def set_application_stage(job_id: int, stage: Any) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE applications SET stage = %s WHERE job_id = %s", (str(stage), int(job_id))
        )


def record_application(*, job_id: int, variant_id: int, cover_letter: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO applications (job_id, variant_id, cover_letter, applied_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (job_id) DO UPDATE SET
                variant_id   = EXCLUDED.variant_id,
                cover_letter = EXCLUDED.cover_letter,
                applied_at   = EXCLUDED.applied_at
            """,
            (int(job_id), int(variant_id), cover_letter),
        )


# ---------- reads (JSON/timestamps returned as text for SQLite parity) ----------


def list_resume_variants() -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, slug, source_path, parsed_json::text AS parsed_json, "
            "tags::text AS tags, updated_at::text AS updated_at "
            "FROM resume_variants ORDER BY slug"
        ).fetchall()


def list_board_jobs(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT j.id, j.title, j.company, j.location, j.state, j.apply_url, "
            "MAX(s.fit_score) AS best_score "
            "FROM jobs j LEFT JOIN scores s ON s.job_id = j.id "
            "GROUP BY j.id ORDER BY (MAX(s.fit_score) IS NULL), MAX(s.fit_score) DESC LIMIT %s",
            (limit,),
        ).fetchall()


def top_matches(min_score: int = 70, limit: int = 10) -> list[dict[str, Any]]:
    """Best-scoring jobs — ONE row per job with its actual winning (max-score) variant."""
    with connect() as conn:
        return conn.execute(
            f"""
            SELECT job_id, title, company, location, apply_url, source, best_score, best_variant
            FROM (
                SELECT DISTINCT ON (j.id)
                    j.id AS job_id, j.title, j.company, j.location, j.apply_url, j.source,
                    s.fit_score AS best_score, rv.slug AS best_variant, j.discovered_at
                FROM jobs j
                JOIN scores s ON s.job_id = j.id
                JOIN resume_variants rv ON rv.id = s.variant_id
                WHERE j.state NOT IN ({sql_values(CLOSED_STATES)}) AND s.fit_score >= %s
                ORDER BY j.id, s.fit_score DESC, s.variant_id ASC
            ) t
            ORDER BY best_score DESC, discovered_at DESC
            LIMIT %s
            """,
            (min_score, limit),
        ).fetchall()


def get_job(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT id, dedup_hash, source, source_job_id, title, company, location,
                   description, description_full, enriched_at::text AS enriched_at,
                   apply_url, posted_date, discovered_at::text AS discovered_at,
                   raw_payload::text AS raw_payload, status, state
            FROM jobs WHERE id = %s
            """,
            (job_id,),
        ).fetchone()


def list_scores_for_job(job_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT rv.slug AS variant, s.fit_score, s.confidence, s.reasoning,
                   s.scored_at::text AS scored_at
            FROM scores s
            JOIN resume_variants rv ON rv.id = s.variant_id
            WHERE s.job_id = %s
            ORDER BY s.fit_score DESC
            """,
            (job_id,),
        ).fetchall()


def find_variant_id_by_slug(slug: str) -> int | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM resume_variants WHERE slug = %s", (slug,)
        ).fetchone()
        return int(row["id"]) if row else None


def raw_select(sql: str) -> list[dict[str, Any]]:
    """ADMIN escape hatch — an ad-hoc READ-ONLY query that bypasses the repo layer.

    Guarded to SELECT/WITH so it can never mutate. Used by analytics (fixed queries)
    and the `hunt db` inspection command; not for application code paths.
    """
    if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
        raise ValueError("raw_select is read-only — SELECT/WITH statements only")
    with connect() as conn:
        conn.read_only = True  # even a piggybacked ';DELETE' can't mutate in a read-only tx
        return conn.execute(sql).fetchall()


# ---------- state machine ----------


def get_job_state(job_id: int) -> str:
    with connect() as conn:
        row = conn.execute("SELECT state FROM jobs WHERE id = %s", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"no job with id={job_id}")
    return row["state"]


def set_job_state(job_id: int, state: Any) -> None:
    with connect() as conn:
        conn.execute("UPDATE jobs SET state = %s WHERE id = %s", (str(state), int(job_id)))


def write_job_transition(
    *, job_id: int, from_state: str | None, to_state: str, reason: str | None = None
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO job_transitions (job_id, from_state, to_state, reason) "
            "VALUES (%s, %s, %s, %s)",
            (int(job_id), from_state, to_state, reason),
        )


def apply_transition(
    *, job_id: int, from_state: str | None, to_state: str, reason: str | None = None,
    event_type: str | None = None, event_class: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Audit + state change + (optional) event append — in ONE transaction (the outbox invariant)."""
    with connect() as conn:  # single connect() == single transaction (commit on clean exit)
        conn.execute(
            "INSERT INTO job_transitions (job_id, from_state, to_state, reason) "
            "VALUES (%s, %s, %s, %s)",
            (int(job_id), from_state, to_state, reason),
        )
        conn.execute("UPDATE jobs SET state = %s WHERE id = %s", (to_state, int(job_id)))
        if event_type is not None:
            conn.execute(
                "INSERT INTO events (type, class, payload) VALUES (%s, %s, %s)",
                (event_type, event_class, Jsonb(payload) if payload is not None else None),
            )


# ---------- event outbox ----------


def write_event(*, type: str, cls: str, payload: dict[str, Any] | None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (type, class, payload) VALUES (%s, %s, %s)",
            (type, cls, Jsonb(payload) if payload is not None else None),
        )


def fetch_unprocessed_events(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, type, class, payload::text AS payload, created_at::text AS created_at, "
            "retry_count FROM events WHERE processed_at IS NULL AND dead_at IS NULL "
            "ORDER BY id LIMIT %s",
            (limit,),
        ).fetchall()


def mark_event_processed(event_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE events SET processed_at = now() WHERE id = %s", (int(event_id),)
        )


def record_event_failure(event_id: int, *, max_retries: int) -> str:
    """Increment retry_count; dead-letter once it reaches max_retries. Returns 'retry'|'dead'."""
    with connect() as conn:
        count = conn.execute(
            "UPDATE events SET retry_count = retry_count + 1 WHERE id = %s RETURNING retry_count",
            (int(event_id),),
        ).fetchone()["retry_count"]
        if count >= max_retries:
            conn.execute(
                "UPDATE events SET dead_at = now() WHERE id = %s", (int(event_id),)
            )
            return "dead"
        return "retry"


# ---------- runs ----------


def create_run(sources: list[str]) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO runs (sources, status, heartbeat_at) VALUES (%s, %s, now()) RETURNING id",
            (Jsonb(sources), "queued"),
        ).fetchone()["id"]


def start_run(run_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = 'running', started_at = now(), heartbeat_at = now() "
            "WHERE id = %s",
            (int(run_id),),
        )


def heartbeat_run(run_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE runs SET heartbeat_at = now() WHERE id = %s", (int(run_id),))


def finish_run(
    run_id: int, status: Any, *, jobs_found: int = 0, jobs_new: int = 0, errors: Any = None
) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = %s, finished_at = now(), jobs_found = %s, jobs_new = %s, "
            "errors = %s WHERE id = %s",
            (str(status), jobs_found, jobs_new,
             Jsonb(errors) if errors is not None else None, int(run_id)),
        )


def request_run_cancel(run_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE runs SET cancel_requested = TRUE WHERE id = %s", (int(run_id),))


def run_cancel_requested(run_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT cancel_requested FROM runs WHERE id = %s", (int(run_id),)
        ).fetchone()
    return bool(row["cancel_requested"]) if row else False


def append_run_log(run_id: int, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET log = log || (now()::text || ' ' || %s || E'\\n') WHERE id = %s",
            (message, int(run_id)),
        )


def get_run(run_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return conn.execute(
            "SELECT id, started_at::text AS started_at, finished_at::text AS finished_at, "
            "sources::text AS sources, jobs_found, jobs_new, errors::text AS errors, "
            "status, heartbeat_at::text AS heartbeat_at, cancel_requested, log "
            "FROM runs WHERE id = %s",
            (int(run_id),),
        ).fetchone()


def list_recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, started_at::text AS started_at, finished_at::text AS finished_at, "
            "sources::text AS sources, jobs_found, jobs_new, errors::text AS errors, "
            "status, heartbeat_at::text AS heartbeat_at, cancel_requested, log "
            "FROM runs ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()


def count_runs_today() -> int:
    """Discovery runs started today (drives the per-day cap)."""
    with connect() as conn:
        return conn.execute(
            "SELECT count(*) AS c FROM runs WHERE started_at::date = CURRENT_DATE"
        ).fetchone()["c"]


def reap_stale_runs(max_age_s: int = 3600) -> int:
    """Mark 'running' runs whose heartbeat is older than max_age_s as failed (crash recovery)."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE runs SET status = %s, finished_at = now() "
            "WHERE status = %s AND (heartbeat_at IS NULL OR heartbeat_at < now() - make_interval(secs => %s))",
            (str(RunStatus.FAILED), str(RunStatus.RUNNING), max_age_s),
        )
        return cur.rowcount


# ---------- search profiles ----------

_PROFILE_COLS = (
    "id, name, keywords, location, pages, exclusions::text AS exclusions, min_salary, "
    "companies_include::text AS companies_include, companies_exclude::text AS companies_exclude, "
    "remote_only, min_yoe, enabled, created_at::text AS created_at"
)


def create_search_profile(
    *, name: str, keywords: str, location: str, pages: int = 1,
    exclusions: list[str] | None = None, min_salary: int | None = None,
    companies_include: list[str] | None = None, companies_exclude: list[str] | None = None,
    remote_only: bool = False, min_yoe: int | None = None,
) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO search_profiles (name, keywords, location, pages, exclusions, "
            "min_salary, companies_include, companies_exclude, remote_only, min_yoe) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (name, keywords, location, pages,
             Jsonb(exclusions) if exclusions is not None else None, min_salary,
             Jsonb(companies_include) if companies_include is not None else None,
             Jsonb(companies_exclude) if companies_exclude is not None else None,
             remote_only, min_yoe),
        ).fetchone()["id"]


def list_search_profiles() -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            f"SELECT {_PROFILE_COLS} FROM search_profiles ORDER BY name"
        ).fetchall()


def list_active_search_profiles() -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            f"SELECT {_PROFILE_COLS} FROM search_profiles WHERE enabled = TRUE ORDER BY name"
        ).fetchall()


def get_search_profile(profile_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return conn.execute(
            f"SELECT {_PROFILE_COLS} FROM search_profiles WHERE id = %s", (int(profile_id),)
        ).fetchone()


def set_search_profile_enabled(profile_id: int, enabled: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE search_profiles SET enabled = %s WHERE id = %s",
            (bool(enabled), int(profile_id)),
        )


# ---------- email triage ----------

_EMAIL_COLS = (
    "id, mailbox, uid, message_id, thread_id, from_addr, from_name, subject, "
    "received_at::text AS received_at, snippet, body_text, category, "
    "extracted::text AS extracted, company_id, job_id, application_id, "
    "action_state, structured_at::text AS structured_at, "
    "created_at::text AS created_at"
)


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
            INSERT INTO email_messages (
                mailbox, uid, message_id, thread_id, from_addr, from_name,
                subject, received_at, snippet, body_text
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (mailbox, uid, message_id, thread_id, from_addr, from_name,
             subject, received_at, snippet, body_text),
        )
        # ON CONFLICT DO NOTHING returns no row — SELECT to get the id.
        if message_id is not None:
            row = conn.execute(
                "SELECT id FROM email_messages WHERE message_id = %s", (message_id,)
            ).fetchone()
            if row is None:  # edge case: conflict was on (mailbox, uid) with different message_id
                row = conn.execute(
                    "SELECT id FROM email_messages WHERE mailbox = %s AND uid = %s",
                    (mailbox, uid),
                ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM email_messages WHERE mailbox = %s AND uid = %s",
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
            "UPDATE email_messages SET category = %s, extracted = %s, structured_at = %s "
            "WHERE id = %s",
            (category, Jsonb(extracted), structured_at, int(email_id)),
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
            "UPDATE email_messages SET company_id = %s, job_id = %s, application_id = %s "
            "WHERE id = %s",
            (company_id, job_id, application_id, int(email_id)),
        )


def set_email_action_state(email_id: int, state: str) -> None:
    """Advance the action lifecycle state of an email."""
    with connect() as conn:
        conn.execute(
            "UPDATE email_messages SET action_state = %s WHERE id = %s",
            (state, int(email_id)),
        )


def get_email_message(email_id: int) -> dict[str, Any] | None:
    """Return one email_messages row by id, or None."""
    with connect() as conn:
        return conn.execute(
            f"SELECT {_EMAIL_COLS} FROM email_messages WHERE id = %s",
            (int(email_id),),
        ).fetchone()


def list_email_messages(
    *,
    category: str | None = None,
    action_state: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return email messages filtered by optional category and/or action_state."""
    conditions: list[str] = []
    params: list[Any] = []
    if category is not None:
        conditions.append("category = %s")
        params.append(category)
    if action_state is not None:
        conditions.append("action_state = %s")
        params.append(action_state)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with connect() as conn:
        return conn.execute(
            f"SELECT {_EMAIL_COLS} FROM email_messages {where} ORDER BY id DESC LIMIT %s",
            params,
        ).fetchall()


def list_unstructured_emails(limit: int = 50) -> list[dict[str, Any]]:
    """Return emails that have not been LLM-structured yet (category IS NULL)."""
    with connect() as conn:
        return conn.execute(
            f"SELECT {_EMAIL_COLS} FROM email_messages WHERE category IS NULL ORDER BY id ASC LIMIT %s",
            (limit,),
        ).fetchall()


def get_sync_state(mailbox: str) -> dict[str, Any] | None:
    """Return the sync cursor row for a mailbox, or None if never synced."""
    with connect() as conn:
        return conn.execute(
            "SELECT mailbox, uidvalidity, last_uid, updated_at::text AS updated_at "
            "FROM email_sync_state WHERE mailbox = %s",
            (mailbox,),
        ).fetchone()


def set_sync_state(*, mailbox: str, uidvalidity: int | None, last_uid: int) -> None:
    """Upsert the IMAP sync cursor for a mailbox."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO email_sync_state (mailbox, uidvalidity, last_uid, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (mailbox) DO UPDATE SET
              uidvalidity = EXCLUDED.uidvalidity,
              last_uid    = EXCLUDED.last_uid,
              updated_at  = now()
            """,
            (mailbox, uidvalidity, last_uid),
        )


def get_application_by_job(job_id: int) -> dict[str, Any] | None:
    """Return the application row (id, stage) for a job, or None if not applied."""
    with connect() as conn:
        return conn.execute(
            "SELECT id, stage FROM applications WHERE job_id = %s", (int(job_id),)
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
        row = conn.execute(
            "INSERT INTO email_actions (email_id, kind, payload, state, created_at) "
            "VALUES (%s, %s, %s, %s, now()::text) RETURNING id",
            (
                int(email_id),
                kind,
                Jsonb(payload),
                str(EmailActionState.PROPOSED),
            ),
        ).fetchone()
        return int(row["id"])


def get_email_action(action_id: int) -> dict[str, Any] | None:
    """Return one email_actions row by id, or None."""
    with connect() as conn:
        return conn.execute(
            "SELECT id, email_id, kind, payload::text AS payload, state, "
            "created_at::text AS created_at, executed_at "
            "FROM email_actions WHERE id = %s",
            (int(action_id),),
        ).fetchone()


def get_latest_action_for_email(email_id: int) -> dict[str, Any] | None:
    """Return the most recent email_actions row for email_id (highest id), or None."""
    with connect() as conn:
        return conn.execute(
            "SELECT id, email_id, kind, payload::text AS payload, state, "
            "created_at::text AS created_at, executed_at "
            "FROM email_actions WHERE email_id = %s ORDER BY id DESC LIMIT 1",
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
            "UPDATE email_actions SET state = %s, executed_at = %s WHERE id = %s",
            (state, executed_at, int(action_id)),
        )


# ---------- content posts ----------


def create_post(*, topic: str | None, source_url: str | None, body: str) -> int:
    """Insert a new content post draft and return its id."""
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO content_posts (topic, source_url, body, created_at) "
            "VALUES (%s, %s, %s, now()::text) RETURNING id",
            (topic, source_url, body),
        ).fetchone()
        return int(row["id"])


def get_post(post_id: int) -> dict[str, Any] | None:
    """Return one content_posts row by id, or None."""
    with connect() as conn:
        return conn.execute(
            "SELECT id, topic, source_url, body, status, created_at "
            "FROM content_posts WHERE id = %s",
            (int(post_id),),
        ).fetchone()


def list_posts(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Return content posts ordered newest-first, optionally filtered by status."""
    with connect() as conn:
        if status is not None:
            return conn.execute(
                "SELECT id, topic, source_url, body, status, created_at "
                "FROM content_posts WHERE status = %s ORDER BY id DESC LIMIT %s",
                (status, limit),
            ).fetchall()
        return conn.execute(
            "SELECT id, topic, source_url, body, status, created_at "
            "FROM content_posts ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()


def set_post_status(post_id: int, status: str) -> None:
    """Update the status column of a content_posts row."""
    with connect() as conn:
        conn.execute(
            "UPDATE content_posts SET status = %s WHERE id = %s", (status, int(post_id))
        )
