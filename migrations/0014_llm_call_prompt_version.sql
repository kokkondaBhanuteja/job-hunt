-- 0014 — record which prompt (name + version) produced each LLM call, so prompt
-- versioning is observable/correlatable in the cost dashboard instead of dead metadata.

ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS prompt_name TEXT;
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS prompt_version INTEGER;
