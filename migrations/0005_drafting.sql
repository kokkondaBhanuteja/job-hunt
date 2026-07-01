-- 0005 — drafting: tailored resumes + cover letters/outreach.

CREATE TABLE IF NOT EXISTS tailored_resumes (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id     BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES resume_variants(id),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, variant_id)
);

CREATE TABLE IF NOT EXISTS drafts (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id     BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL CHECK (kind IN ('cover', 'outreach')),
    body       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_drafts_job ON drafts(job_id);
