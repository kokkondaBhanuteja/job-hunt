-- 0015 — the user's single career-context blob (pasted md/json), injected into every AI prompt.

CREATE TABLE IF NOT EXISTS user_context (
    id         INTEGER PRIMARY KEY CHECK (id = 1),   -- singleton: one active context
    content    TEXT NOT NULL,
    format     TEXT NOT NULL CHECK (format IN ('md', 'json')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
