-- 0002 — job state machine, in-DB event outbox, and run lifecycle.
-- CHECK value lists mirror job_hunt/enums.py (JobState, RunStatus).

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'discovered'
        CHECK (state IN ('discovered','enriched','scored','opportunity','archived',
                         'tailoring_ready','drafted','review_pending','ready_to_apply',
                         'applied','oa','interview','hr','offer','rejected','deferred','withdrawn'));
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);

CREATE TABLE IF NOT EXISTS job_transitions (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id     BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    from_state TEXT,
    to_state   TEXT NOT NULL,
    reason     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_job_transitions_job ON job_transitions(job_id);

CREATE TABLE IF NOT EXISTS events (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type         TEXT NOT NULL,
    class        TEXT NOT NULL,
    payload      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_events_unprocessed ON events(processed_at) WHERE processed_at IS NULL;

ALTER TABLE runs
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','cancelled','failed','done'));
ALTER TABLE runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS log TEXT NOT NULL DEFAULT '';
