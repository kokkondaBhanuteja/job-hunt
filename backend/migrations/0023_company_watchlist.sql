-- 0023 — company watchlist: watch specific companies' ATS boards for new postings.

CREATE TABLE IF NOT EXISTS company_watchlist (
    id          SERIAL PRIMARY KEY,
    company     TEXT NOT NULL,
    ats         TEXT NOT NULL CHECK (ats IN ('greenhouse', 'lever', 'workday', 'ashby', 'smartrecruiters', 'icims', 'naukri', 'remoteok', 'workable', 'unknown')),
    board_token TEXT NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
