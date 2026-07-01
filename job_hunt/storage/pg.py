"""Postgres repository (psycopg3) — the production datastore.

Mirrors the function surface of `storage/db.py` (the SQLite test backend) so the
`storage.repo` façade can swap between them with zero changes at call sites.

Compatibility note: JSON/timestamp columns are returned **as text** (`::text`) so
downstream code that does `json.loads(parsed_json)` or treats `*_at` as ISO strings
behaves identically to the SQLite backend.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from job_hunt.enums import CLOSED_STATES, JobStatus, sql_values

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
) -> int | None:
    """Insert a job; return its id, or None if the dedup_hash already existed."""
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
        return int(row["id"]) if row else None


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
            WHERE state IN ('discovered', 'enriched', 'scored', 'opportunity')
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


def set_job_enriched(job_id: int, description_full: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET description_full = %s, enriched_at = now() WHERE id = %s",
            (description_full, int(job_id)),
        )


# ---------- drafting ----------


def best_scored_variant(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT rv.id, rv.slug, rv.parsed_json::text AS parsed_json
            FROM scores s JOIN resume_variants rv ON rv.id = s.variant_id
            WHERE s.job_id = %s ORDER BY s.fit_score DESC LIMIT 1
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


def save_company(
    *, name: str, size: str | None = None, funding_stage: str | None = None,
    tech: list[str] | None = None, glassdoor: str | None = None, notes: str | None = None,
) -> int:
    with connect() as conn:
        return conn.execute(
            """
            INSERT INTO companies (name, size, funding_stage, tech, glassdoor, notes, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (name) DO UPDATE SET
              size = EXCLUDED.size, funding_stage = EXCLUDED.funding_stage,
              tech = EXCLUDED.tech, glassdoor = EXCLUDED.glassdoor,
              notes = EXCLUDED.notes, fetched_at = now()
            RETURNING id
            """,
            (name, size, funding_stage, Jsonb(tech) if tech is not None else None,
             glassdoor, notes),
        ).fetchone()["id"]


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


def save_checkpoint(*, job_id: int, step: int, data: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO apply_checkpoints (job_id, step, data, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (job_id) DO UPDATE SET
              step = EXCLUDED.step, data = EXCLUDED.data, updated_at = now()
            """,
            (int(job_id), int(step), Jsonb(data)),
        )


def get_checkpoint(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return conn.execute(
            "SELECT id, job_id, step, data::text AS data, updated_at::text AS updated_at "
            "FROM apply_checkpoints WHERE job_id = %s",
            (int(job_id),),
        ).fetchone()


def clear_checkpoint(job_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM apply_checkpoints WHERE job_id = %s", (int(job_id),))


def save_submitted_resume(*, job_id: int, variant_id: int | None, content: str) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO submitted_resumes (job_id, variant_id, content) "
            "VALUES (%s, %s, %s) RETURNING id",
            (int(job_id), variant_id, content),
        ).fetchone()["id"]


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


def list_learnings_for_job(job_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, job_id, variant_id, kind, payload::text AS payload, "
            "created_at::text AS created_at FROM learnings WHERE job_id = %s ORDER BY id DESC",
            (int(job_id),),
        ).fetchall()


def write_llm_call(
    *, task: str, provider: str, model: str, prompt: str | None, response: str | None,
    prompt_tokens: int | None = None, completion_tokens: int | None = None,
    cost: float | None = None, latency_ms: int | None = None,
    ok: bool = True, error: str | None = None,
) -> None:
    """Best-effort observability log. Never raises."""
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (
                    task, provider, model, prompt, response, prompt_tokens,
                    completion_tokens, cost, latency_ms, ok, error
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (str(task), str(provider), model, prompt, response, prompt_tokens,
                 completion_tokens, cost, latency_ms, ok, error),
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


def set_job_status(job_id: int, status: JobStatus | str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = %s WHERE id = %s", (str(status), int(job_id))
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


def list_jobs_for_scoring(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT j.id, j.title, j.company, j.location, j.source, j.description
            FROM jobs j
            LEFT JOIN scores s ON s.job_id = j.id
            WHERE j.status = %s AND s.id IS NULL
            LIMIT %s
            """,
            (str(JobStatus.NEW), limit),
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
                ORDER BY j.id, s.fit_score DESC
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
            "SELECT id, type, class, payload::text AS payload, created_at::text AS created_at "
            "FROM events WHERE processed_at IS NULL ORDER BY id LIMIT %s",
            (limit,),
        ).fetchall()


def mark_event_processed(event_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE events SET processed_at = now() WHERE id = %s", (int(event_id),)
        )


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
