-- 0019 — expand drafts.kind CHECK to include message-draft types.

ALTER TABLE drafts DROP CONSTRAINT IF EXISTS drafts_kind_check;
ALTER TABLE drafts ADD CONSTRAINT drafts_kind_check
    CHECK (kind IN ('cover', 'outreach', 'thank_you', 'follow_up', 'negotiation'));
