-- 0007 — learnings: what outcomes taught us (feeds future tailoring).

CREATE TABLE IF NOT EXISTS learnings (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id     BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    variant_id BIGINT REFERENCES resume_variants(id),
    kind       TEXT NOT NULL,
    payload    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_learnings_job ON learnings(job_id);
