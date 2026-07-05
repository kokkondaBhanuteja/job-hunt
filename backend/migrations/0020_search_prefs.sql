-- 0020 — the user's job-search preferences (pasted md), parsed by the LLM into search profiles.

CREATE TABLE IF NOT EXISTS search_prefs (
    id         INTEGER PRIMARY KEY CHECK (id = 1),   -- singleton: one active prefs blob
    content    TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
