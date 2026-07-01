-- 0013 — indexes on FK columns used by JOINs / ON DELETE CASCADE (were seq-scanning).

CREATE INDEX IF NOT EXISTS idx_applications_variant ON applications(variant_id);
CREATE INDEX IF NOT EXISTS idx_scores_variant       ON scores(variant_id);
CREATE INDEX IF NOT EXISTS idx_submitted_job        ON submitted_resumes(job_id);
CREATE INDEX IF NOT EXISTS idx_submitted_variant    ON submitted_resumes(variant_id);
