-- 0004 — full-JD enrichment + idempotent (re)scoring.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description_full TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;

ALTER TABLE scores ADD COLUMN IF NOT EXISTS scored_against TEXT;   -- 'snippet' | 'full'
ALTER TABLE scores ADD COLUMN IF NOT EXISTS input_hash TEXT;       -- hash of the JD text scored
ALTER TABLE scores ADD COLUMN IF NOT EXISTS provider_model TEXT;   -- provider/model used
