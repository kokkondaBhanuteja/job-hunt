-- 0022 — apply-policy singleton: minimum fit score, must-have / avoid keywords,
--         seniority, and remote-only preference. Filters which scored jobs surface
--         as "ready to apply" candidates for human review. Never auto-applies.

CREATE TABLE IF NOT EXISTS apply_policy (
    id         INTEGER PRIMARY KEY CHECK (id = 1),   -- singleton: one active policy
    policy     JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
