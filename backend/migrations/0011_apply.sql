-- 0011 — apply subsystem: crash-resumable checkpoints + submitted-résumé snapshots.

CREATE TABLE IF NOT EXISTS apply_checkpoints (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id     BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step       INTEGER NOT NULL,
    data       JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id)
);

CREATE TABLE IF NOT EXISTS submitted_resumes (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id       BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id   BIGINT REFERENCES resume_variants(id),
    content      TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
