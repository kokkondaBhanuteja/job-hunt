-- 0008 — pgvector semantic search. 768-dim matches nomic-embed-text / EMBED_DIM.
-- (No ANN index yet — exact search is fine at single-user scale; add HNSW later.)

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE jobs            ADD COLUMN IF NOT EXISTS embedding vector(768);
ALTER TABLE resume_variants ADD COLUMN IF NOT EXISTS embedding vector(768);
