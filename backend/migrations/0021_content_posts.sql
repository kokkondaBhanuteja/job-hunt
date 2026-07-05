-- 0021 — content posts: AI-drafted tech post drafts for LinkedIn/X (never auto-posted).
CREATE TABLE IF NOT EXISTS content_posts (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic       TEXT,
    source_url  TEXT,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'posted', 'dismissed')),
    created_at  TEXT NOT NULL DEFAULT now()::text
);
CREATE INDEX IF NOT EXISTS idx_content_posts_status ON content_posts(status);
