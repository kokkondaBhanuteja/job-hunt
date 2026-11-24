-- 0025 — cold-email sending on the existing (previously unused) outreach table.
-- Additive only; no backfill needed because nothing wrote to outreach before this.

ALTER TABLE outreach ADD COLUMN IF NOT EXISTS to_email   TEXT;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS status     TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'sending', 'sent', 'failed', 'replied', 'cancelled'));
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS parent_id  BIGINT REFERENCES outreach(id) ON DELETE CASCADE;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS message_id TEXT;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS last_error TEXT;  -- not "error": services treat an "error" key as failure
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS replied_at TIMESTAMPTZ;

-- At most one follow-up per original email (NULL parent_ids never collide).
CREATE UNIQUE INDEX IF NOT EXISTS uq_outreach_parent ON outreach(parent_id);
CREATE INDEX IF NOT EXISTS idx_outreach_status_sent ON outreach(status, sent_at);
