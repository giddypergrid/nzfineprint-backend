# Fine Print

A search and research tool over the New Zealand Gazette — the official public record of company
liquidations, receiverships, removals, appointments, and land and legal notices. It answers the
questions the raw record can't: *should I worry about this company, what's happening near me, who is
behind these failures.*

**205,246 notices** — pulled, structured, embedded, and searchable.

## What it does

- **Search** — one endpoint auto-routes each query. Short keyword/name lookups hit Postgres
  full-text directly (~milliseconds, no LLM); natural-language questions are parsed by an LLM into
  filters + intent and answered by semantic vector search.
- **Research agent** — for questions a single search can't answer, an agent chains multiple lookups
  (find an entity → trace its timeline → read the key notice → surface who else is connected) and
  writes a plain-language answer, adapting its tone to how the question is asked.

## How it's built

```
DigitalNZ API ──pull──> notices.jsonl ──load──> Postgres ──enrich──> structured fields
                                                     │                (LLM: headline, category,
                                                     │                 significance, parties)
                                                     └──vectorize──> pgvector embeddings (local GPU)

                                    ┌─────────────── app/ (FastAPI) ───────────────┐
                                    │  /search  — hybrid keyword + semantic         │
                                    │  agent/   — multi-step research over the tools│
                                    └───────────────────────────────────────────────┘
```

- **Storage / search:** Postgres 17 + pgvector + pg_trgm, hybrid full-text and vector retrieval.
- **Embeddings:** bge-large-en-v1.5 (1024-dim), documents embedded on a local GPU, queries via a
  weightless hosted call (verified byte-identical to the local vectors).
- **LLM:** DeepSeek — reasoning-off for bulk enrichment (cost), reasoning-on for the agent (planning).
- **Offline pipeline:** four resumable, idempotent stages (pull → load → enrich → vectorize).

## Why it's built this way

The interesting part of this project is the engineering judgment, not the feature list. The stemming
bug that made "liquidation" match chemical notices, why the query router is deliberately *dumb*, why
the agent's tools return headlines instead of full text, why a round cap is a cost ceiling — those
calls and their tradeoffs are written up in **[DECISIONS.md](DECISIONS.md)**.

## Running it

See [memory / key steps] for the full stack commands. In short: Postgres runs in Docker, the four
pipeline stages run from `Prep/`, and the API runs from the repo root with its own venv.

## Status

Offline pipeline complete (205,246 notices loaded, enriched, embedded). Search live. Research agent
built and tested. **Not yet publicly deployed** — auth and rate-limiting on the LLM routes are the
remaining blocker (see DECISIONS.md → Known gaps).
