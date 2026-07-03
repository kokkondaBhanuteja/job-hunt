-- 0003 — saved searches. Discovery runs once per ACTIVE profile.

CREATE TABLE IF NOT EXISTS search_profiles (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name              TEXT UNIQUE NOT NULL,
    keywords          TEXT NOT NULL,
    location          TEXT NOT NULL,
    pages             INTEGER NOT NULL DEFAULT 1,
    exclusions        JSONB,
    min_salary        INTEGER,
    companies_include JSONB,
    companies_exclude JSONB,
    remote_only       BOOLEAN NOT NULL DEFAULT FALSE,
    min_yoe           INTEGER,
    enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
