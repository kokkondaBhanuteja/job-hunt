-- 0010 — company research cache + memory.

CREATE TABLE IF NOT EXISTS companies (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          TEXT UNIQUE NOT NULL,
    size          TEXT,
    funding_stage TEXT,
    tech          JSONB,
    glassdoor     TEXT,
    notes         TEXT,
    fetched_at    TIMESTAMPTZ
);
