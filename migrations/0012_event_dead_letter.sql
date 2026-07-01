-- 0012 — outbox dead-lettering: a handler that keeps failing must not block the queue.

ALTER TABLE events ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE events ADD COLUMN IF NOT EXISTS dead_at TIMESTAMPTZ;
