-- 0018 — email actions: proposed/confirmed/executed actions on email messages.
CREATE TABLE IF NOT EXISTS email_actions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email_id    BIGINT NOT NULL REFERENCES email_messages(id),
    kind        TEXT NOT NULL CHECK (kind IN ('draft_reply', 'apply_label', 'archive')),
    payload     JSONB,
    state       TEXT NOT NULL DEFAULT 'proposed'
                    CHECK (state IN ('none', 'proposed', 'confirmed', 'executed', 'failed', 'dismissed')),
    created_at  TEXT NOT NULL DEFAULT now()::text,
    executed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_email_actions_email_id ON email_actions(email_id);
