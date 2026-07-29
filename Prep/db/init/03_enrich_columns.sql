-- Enrichment columns (added 2026-07). Safe to re-run. On a fresh container these already
-- exist from 01_schema.sql; this migration brings an already-loaded DB up to the same shape.

ALTER TABLE notices ADD COLUMN IF NOT EXISTS headline            text;
ALTER TABLE notices ADD COLUMN IF NOT EXISTS event_category      text;
ALTER TABLE notices ADD COLUMN IF NOT EXISTS action_taken        text;
ALTER TABLE notices ADD COLUMN IF NOT EXISTS affected_parties    jsonb;
ALTER TABLE notices ADD COLUMN IF NOT EXISTS significance_reason text;
ALTER TABLE notices ADD COLUMN IF NOT EXISTS enriched_at         timestamptz;

-- Filter/sort the enriched fields fast.
CREATE INDEX IF NOT EXISTS notices_event_category_idx ON notices (event_category);
CREATE INDEX IF NOT EXISTS notices_significance_idx   ON notices (significance_score DESC);
