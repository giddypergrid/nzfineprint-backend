# Fine Print

Search the New Zealand Gazette, the official public record where liquidations, receiverships,
company removals, bankruptcies, and land and legal notices are published.

**Live at [nzfineprint.com](https://www.nzfineprint.com)** · API at `api.nzfineprint.com` · frontend
in [nzfineprint-frontend](https://github.com/giddypergrid/nzfineprint-frontend)

Not affiliated with the New Zealand Gazette or any government agency.

## The idea

Everything that happens to a company in New Zealand ends up in the Gazette, and almost nobody reads
it. The notices are public but they are written for lawyers: dense, templated, and searchable only
one notice at a time. If your builder went into liquidation last month, the record says so, you
just have no realistic way to find out.

So I pulled all of it, had an LLM rewrite each one in plain English and tag it, embedded it, and put
a search box in front. Two ways in:

- **Search** a company name, get every notice naming it.
- **Ask a question** in plain English and an agent does the digging: find the entity, trace its
  timeline, read the notices that matter, say who else is involved, then write the answer with its
  sources.

The second one is the actual point. Search finds documents; the question you really have is "should
I worry about this company", and that takes several lookups and some reading.

## What is in it

**206,431 notices, 13 January 2000 to 2 September 2026.** Every one carries a plain-English
rewrite, an event category, an action type, a significance score and a 1024-dimension embedding.
The pipeline runs nightly, so the numbers below move.

```
2000  ████████████████████████████████████████████████████████████████████████████     9,271
2001  ██████████████████████████████████████████████████████████████████████████       8,814
2002  ██████████████████████████████████████████████████████████████████████           8,387
2003  ██████████████████████████████████████████████████████████████████████           8,361
2004  ████████████████████████████████████████████████████████████████████████         8,560
2005  ████████████████████████████████████████████████████████████████████████         8,624
2006  ██████████████████████████████████████████████████████████████████████████       8,880
2007  ██████████████████████████████████████████████████████████████████████████       8,775
2008  ████████████████████████████████████████████████████████████████████████████████ 9,652
2009  ████████████████████████████████████████████████████████████████████████████████ 10,389  ← peak
2010  ████████████████████████████████████████████████████████████████████████████████ 9,777
2011  ██████████████████████████████████████████████████████████████████████████       8,824
2012  ██████████████████████████████████████████████████████████████████████           8,420
2013  ████████████████████████████████████████████████████████████████████             8,108
2014  ██████████████████████████████████████████████████████████████                   7,736
2015  ████████████████████████████████████████████████████████████                     7,415
2016  ██████████████████████████████████████████████████████████                       7,235
2017  ████████████████████████████████████████████████████                             6,604
2018  ██████████████████████████████████████████████                                   6,295
2019  ██████████████████████████████████████                                           5,154  ← low
2020  ████████████████████████████████████████                                         5,722
2021  ██████████████████████████████████████                                           5,472
2022  ████████████████████████████████████████                                         5,592
2023  ██████████████████████████████████████████                                       5,795
2024  ██████████████████████████████████████████████                                   6,362
2025  ██████████████████████████████████████████████████████                           7,325
2026  ██████████████████████████████████                                               4,882  (to Sep)
```

The dip through 2019 and the climb since 2022 are in the record itself, not an artefact of the pull.
Live counts come from `GET /stats`, which reads Redis.

Each notice is tagged from a fixed vocabulary the LLM has to choose from, 13 event categories
(liquidation, receivership, administration, bankruptcy, cessation, company_removal,
creditor_meeting, claim_deadline, legislation, land, charity_or_society, appointment, other) and 16
action types. The query parser may only build filters from those exact strings, so a parsed filter
always matches real stored data.

## How it fits together

```
DigitalNZ API --pull--> notices.jsonl --load--> Postgres --enrich--> plain English, category,
                                                    |               significance, parties  (DeepSeek)
                                                    +--vectorize--> pgvector embeddings   (bge-m3)

                    app/ (FastAPI)
                      /search          keyword or semantic, routed by query shape
                      /ask/stream      the research agent, streamed step by step
                      /notices/{id}    one notice
                      /stats           corpus size, served from Redis
```

Postgres 17 with pgvector holds everything, rows, full-text and vectors in one database. DeepSeek
does the enrichment and the agent's reasoning. Embeddings are bge-m3 over a hosted API, both for
documents and for queries, so there is no model weight on the server at all.

### Three ways a query is answered

```
                    how many words?
                          │
        ≤ 3 words ────────┴──────── > 3 words              a question
            │                          │                        │
     phraseto_tsquery            DeepSeek pulls out       agent loop, 4 read-only
     + ts_rank on the            filters and a clean      tools, max 6 rounds,
     full text. No LLM,          phrase, then cosine      cites every notice
     no embedding call.          search over the          it used
                                 plain-English summaries
```

Routing is a word count in `search/query_parser.py`, `_MAX_KEYWORD_WORDS = 3`. A name is three words
or fewer nearly always, and a name is exactly the case where full-text is both cheaper and better
than a vector. The agent is a separate endpoint, not a fallback.

## Where to look

If you only read four files, read these.

| File | Why |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | The judgement calls, written up properly. Start here. |
| [`app/search/query_parser.py`](app/search/query_parser.py) | The routing rule, and why it is a word count instead of a classifier |
| [`app/agent/loop.py`](app/agent/loop.py) | The agent: tool loop, round cap, how the answer gets its citations |
| [`app/agent/tool_specs.py`](app/agent/tool_specs.py) | The four tools the model can see, and the narration argument that makes progress visible |

Then, by area:

```
Prep/pipeline/     pull → load → enrich → vectorize, each stage resumable
Prep/db/init/      schema, then indexes as a separate file (order matters, see below)
app/search/        engine.py runs it, facets.py holds the enum vocabulary
app/ratelimit.py   Redis counters, so limits hold across workers
app/tests/         search_probe.py, the regression probe
```

## Decisions

The full write-up is in **[DECISIONS.md](DECISIONS.md)**: the stemming bug that made "liquidation"
match chemical notices, why the query router is deliberately dumb, why the agent's tools return
headlines instead of full text, why the round cap is a cost ceiling. The ones that shaped it most:

- **Search demands adjacent words.** The looser version matched words borrowed from three different
  companies inside one bulk-removal list and confidently named the wrong company. Telling someone
  their supplier is in liquidation when it isn't costs far more than making them retype a name.
- **The trigram typo-tolerance was deleted.** Measured against the real data, no threshold separated
  its rescues from its false positives. "Bay Plumbing Limited" scored higher against HOULAHAN
  PLUMBING LIMITED than a genuine near-miss did against its real match.
- **Relevance picks the results, date orders them.** Two stages, not one. Sorting by date in the same
  query silently discards relevance entirely on the semantic route, because there the `WHERE` clause
  is independent of the query.
- **Indexes are built after the bulk load, not before.** Separate SQL file, run second. Inserting
  205k rows into an already-indexed table is far slower.
- **The backend owns every limit.** The model asks; the code decides how much gets fetched.
- **Rate limits on anything that costs money**, counted in Redis so they hold across workers.
- **The nightly load is delta-only**, keyed on a byte offset into the pull file. It used to re-upsert
  all 205k rows every night.

## What is not done

- **Location is best-effort.** There is no region column, place names live loose in the notice text,
  so "near me" is a search term and not a real filter. Region enrichment is the highest-value thing
  to add next.
- **No accounts, no watchlists.** You cannot ask it to tell you when something new is filed against a
  name, which is the obvious next feature and the reason to come back.
- **Evaluation is by inspection.** I verified search and agent quality by hand against the live
  database. There is a regression probe at `app/tests/search_probe.py` but no real eval harness.
- **No bot check on the Ask button.** Cloudflare sits in front of the API, but a Turnstile check on
  the expensive route is still worth adding.

---

Python 3.11, FastAPI, Postgres 17 + pgvector, Redis, Docker Compose. DeepSeek for enrichment and
agent reasoning, bge-m3 for embeddings. Frontend is React and TypeScript on Vercel.

Running it needs three `.env` files (all have an `.env.example` beside them), then
`docker compose up -d` for db, redis and api, and `cd web && npm run dev` for the frontend. The four
pipeline stages are separate `docker compose run` commands and each one only processes what the
previous stage left for it, so re-running is safe.

Data is from the New Zealand Gazette via DigitalNZ, CC BY 3.0 NZ.
