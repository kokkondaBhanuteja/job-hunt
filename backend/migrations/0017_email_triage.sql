-- 0017 — email triage: inbound message store + per-mailbox sync state.
CREATE TABLE IF NOT EXISTS email_messages (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mailbox         TEXT NOT NULL,
    uid             INTEGER NOT NULL,
    message_id      TEXT,
    thread_id       TEXT,
    from_addr       TEXT,
    from_name       TEXT,
    subject         TEXT,
    received_at     TIMESTAMPTZ,
    snippet         TEXT,
    body_text       TEXT,
    category        TEXT CHECK (category IS NULL OR category IN (
                        'recruiter_outreach', 'interview_invite', 'rejection',
                        'application_confirmation', 'other')),
    extracted       JSONB,
    company_id      INTEGER REFERENCES companies(id),
    job_id          INTEGER REFERENCES jobs(id),
    application_id  INTEGER REFERENCES applications(id),
    action_state    TEXT NOT NULL DEFAULT 'none'
                        CHECK (action_state IN (
                            'none', 'proposed', 'confirmed', 'executed', 'failed', 'dismissed')),
    structured_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (message_id),
    UNIQUE (mailbox, uid)
);
CREATE INDEX IF NOT EXISTS idx_email_messages_category     ON email_messages(category);
CREATE INDEX IF NOT EXISTS idx_email_messages_action_state ON email_messages(action_state);

CREATE TABLE IF NOT EXISTS email_sync_state (
    mailbox     TEXT PRIMARY KEY,
    uidvalidity INTEGER,
    last_uid    INTEGER NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
