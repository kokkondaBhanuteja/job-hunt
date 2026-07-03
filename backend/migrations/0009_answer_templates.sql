-- 0009 — reusable, truthful screening-question answers.

CREATE TABLE IF NOT EXISTS answer_templates (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_pattern TEXT NOT NULL,
    answer_text      TEXT NOT NULL,
    tags             JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
