-- 0016 — standing application answers a résumé does not carry (single active row).
CREATE TABLE IF NOT EXISTS applicant_profile (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    first_name          TEXT,
    last_name           TEXT,
    email               TEXT,
    phone               TEXT,
    location            TEXT,
    linkedin_url        TEXT,
    github_url          TEXT,
    portfolio_url       TEXT,
    work_authorization  TEXT,
    needs_sponsorship   BOOLEAN,
    willing_to_relocate BOOLEAN,
    notice_period       TEXT,
    expected_ctc        TEXT,
    current_ctc         TEXT,
    years_experience    TEXT,
    referral_source     TEXT,
    extra               JSONB,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
