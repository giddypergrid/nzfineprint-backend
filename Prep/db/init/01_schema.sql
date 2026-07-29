-- Fine Print — notices table. One row per Gazette notice, keyed on its id.
-- Run by piping this file into the db container (see command in chat / README).

CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector: semantic embeddings
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy / typo-tolerant text matching

CREATE TABLE IF NOT EXISTS notices (
    -- straight from the jsonl pull
    id              text PRIMARY KEY,       -- "2000-ds7832" — natural key, drives the upsert
    code            text,                   -- 2-letter type code, e.g. "ds"
    type            text,                   -- human label, e.g. "Removals"
    date            date,                   -- publication day
    title           text,
    nzbn            text,                   -- 13-digit company key, nullable (post-2013)
    company_number  text,                   -- older/regional id, nullable
    fulltext        text,                   -- the notice body — the thing we search
    landing_url     text,
    source          text,

    -- filled later by offline enrichment (all nullable until then)
    headline           text,                -- one-line scannable summary
    plain_english      text,                -- full plain-language decode (2-3 sentences)
    event_category     text,                -- normalized enum, e.g. "receivership" (see enrich.py)
    action_taken       text,                -- normalized enum, e.g. "receiver_appointed"
    affected_parties   jsonb,               -- ["ASB Bank Limited", "Prestige Management Ltd"]
    significance_score int,                 -- buried-lede / importance, 0-100
    significance_reason text,               -- one line justifying the score (audit trail)
    enriched_at        timestamptz,         -- when enrichment last ran (NULL = not yet)
    embedding          vector(1024),        -- semantic vector (dim depends on chosen model)

    loaded_at       timestamptz DEFAULT now()
);
