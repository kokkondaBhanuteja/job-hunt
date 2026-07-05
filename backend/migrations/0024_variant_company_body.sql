-- 0024 — per-company résumé variants: add company, body; allow source_path to be NULL.

ALTER TABLE resume_variants ALTER COLUMN source_path DROP NOT NULL;

ALTER TABLE resume_variants ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE resume_variants ADD COLUMN IF NOT EXISTS body    TEXT;
