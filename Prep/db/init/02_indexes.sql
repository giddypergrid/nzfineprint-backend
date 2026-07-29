-- Run after the table is loaded. Safe to re-run (all IF NOT EXISTS).

-- Full-text: a generated column that auto-derives from title + fulltext, kept in sync by Postgres.
-- 'simple' (no stemming) on purpose: 'english' collapsed liquidation/liquidator/liquid to one stem,
-- so a liquidation search matched chemical "liquid" notices. 'simple' matches whole words as typed.
ALTER TABLE notices ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(fulltext, ''))) STORED;

CREATE INDEX IF NOT EXISTS notices_search_idx ON notices USING GIN (search_vector);

-- Fuzzy / typo-tolerant company name matching (pg_trgm, enabled in schema.sql).
CREATE INDEX IF NOT EXISTS notices_title_trgm_idx ON notices USING GIN (title gin_trgm_ops);

-- Semantic search: HNSW proximity graph over the embedding column. Without this, every semantic
-- query sequentially scans all 205k vectors (~7s); with it, milliseconds. Must match the distance
-- operator the query uses — engine.py uses `<=>` (cosine), so vector_cosine_ops.
-- Build note: parallel workers need shared memory, and Postgres containers default to a 64MB
-- /dev/shm, which fails with "could not resize shared memory segment". docker-compose.yml now sets
-- shm_size; if you still hit it, `SET max_parallel_maintenance_workers = 0` before creating.
CREATE INDEX IF NOT EXISTS notices_embedding_hnsw_idx ON notices USING hnsw (embedding vector_cosine_ops);

-- Hard filters: exact-match lookups and date ranges.
CREATE INDEX IF NOT EXISTS notices_code_idx ON notices (code);
CREATE INDEX IF NOT EXISTS notices_date_idx ON notices (date);
CREATE INDEX IF NOT EXISTS notices_nzbn_idx ON notices (nzbn);
CREATE INDEX IF NOT EXISTS notices_company_number_idx ON notices (company_number);
