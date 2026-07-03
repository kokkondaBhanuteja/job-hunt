-- 0001_init — initial Postgres schema (port of the v0 SQLite schema).
-- CHECK value lists mirror job_hunt/enums.py (JobStatus, ReplyType); a test asserts
-- they stay in sync. State-machine / event-bus tables arrive in a later migration.

CREATE TABLE IF NOT EXISTS resume_variants (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    source_path TEXT NOT NULL,
    parsed_json JSONB NOT NULL,
    tags        JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dedup_hash    TEXT UNIQUE NOT NULL,          -- canonical: company|title|location
    source        TEXT NOT NULL,
    source_job_id TEXT,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    location      TEXT,
    description   TEXT,
    apply_url     TEXT NOT NULL,
    posted_date   TEXT,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload   JSONB,
    status        TEXT NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new', 'ready-to-review', 'applied', 'skipped', 'saved'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);

CREATE TABLE IF NOT EXISTS scores (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id     BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES resume_variants(id) ON DELETE CASCADE,
    fit_score  INTEGER NOT NULL,
    confidence INTEGER,
    reasoning  TEXT NOT NULL,
    scored_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(job_id, variant_id)
);
CREATE INDEX IF NOT EXISTS idx_scores_job ON scores(job_id);
CREATE INDEX IF NOT EXISTS idx_scores_fit ON scores(fit_score DESC);

CREATE TABLE IF NOT EXISTS applications (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id       BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id   BIGINT NOT NULL REFERENCES resume_variants(id),
    cover_letter TEXT NOT NULL,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    reply_type   TEXT CHECK (reply_type IS NULL OR reply_type IN ('interview', 'reject', 'next-step')),
    reply_notes  TEXT,
    UNIQUE(job_id)
);

CREATE TABLE IF NOT EXISTS contacts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company      TEXT NOT NULL,
    name         TEXT NOT NULL,
    role         TEXT,
    persona      TEXT,
    email_guess  TEXT,
    linkedin_url TEXT,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(company, name)
);

CREATE TABLE IF NOT EXISTS outreach (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contact_id    BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    job_id        BIGINT REFERENCES jobs(id),
    template_slug TEXT NOT NULL,
    subject       TEXT NOT NULL,
    body          TEXT NOT NULL,
    mailto_url    TEXT NOT NULL,
    drafted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at       TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS runs (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    sources    JSONB NOT NULL,
    jobs_found INTEGER NOT NULL DEFAULT 0,
    jobs_new   INTEGER NOT NULL DEFAULT 0,
    errors     JSONB
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task              TEXT NOT NULL,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    prompt            TEXT,
    response          TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost              DOUBLE PRECISION,
    latency_ms        INTEGER,
    ok                BOOLEAN NOT NULL DEFAULT TRUE,
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_task ON llm_calls(task);
