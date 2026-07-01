-- 0006 — interview-pipeline stage on applications (powers the funnel analytics).

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT 'applied'
        CHECK (stage IN ('applied', 'oa', 'interview', 'hr', 'offer', 'rejected'));
