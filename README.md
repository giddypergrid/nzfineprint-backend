# Fine Print

Search the New Zealand Gazette — the official public record where liquidations, receiverships,
company removals, bankruptcies, and land and legal notices are published.

Live at **[nzfineprint.com](https://www.nzfineprint.com)**. API at `api.nzfineprint.com`.
Not affiliated with the New Zealand Gazette or any government agency.

## The idea

Everything that happens to a company in New Zealand ends up in the Gazette, and almost nobody reads
it. The notices are public but they are written for lawyers: dense, templated, and searchable only
one notice at a time. If your builder went into liquidation last month, the record says so — you
just have no realistic way to find out.

So I pulled all of it (about 205,000 notices back to 2000, growing nightly), had an LLM rewrite each
one in plain English and tag it, embedded it, and put a search box in front. Two ways in:

- **Search** — type a company name, get every notice naming it.
- **Ask a question** — describe a situation in plain English and an agent does the digging: find the
  entity, trace its timeline, read the notices that matter, say who else is involved, then write the
  answer with its sources.

The second one is the actual point. Search finds documents; the question you really have is "should
I worry about this company", and that takes several lookups and some reading.

## Using it

Just go to the site. Nothing to install, no account.

A name has to be spelled the way it is registered — search requires the words to be **adjacent**, so
"Bay Plumbing Limited" will not match a notice that happens to contain "Bay" and "Plumbing"
somewhere. That is deliberate; see the decisions below. Zero results genuinely means it is not in
the record.

## Running it locally

Three env files, all from the `.env.example` next to them: `./.env` (Postgres user/password),
`app/.env` (`DEEPSEEK_API_KEY`, `EMBED_API_KEY`), `Prep/.env` (those plus `DIGITALNZ_API_KEY`).

```bash
docker compose up -d           # db + redis + api on :8000
cd web && npm install && npm run dev    # frontend on :5173, proxies /api to the backend
```

The offline pipeline is four resumable stages. Each one only processes what the previous stage left
for it, so re-running is safe and picks up where it stopped:

```bash
docker compose run --rm prep python -m pipeline.pull        # DigitalNZ -> notices.jsonl
docker compose run --rm prep python -m pipeline.load        # jsonl -> Postgres
docker compose run --rm prep python -m pipeline.enrich      # LLM -> plain English, category, parties
docker compose run --rm prep python -m pipeline.vectorize   # -> pgvector embeddings

docker compose run --rm prep sh run_update.sh               # all of the above, incremental
docker compose --profile schedule up -d updater             # same thing nightly at midnight NZ
```

First-time setup on a fresh database creates the table, loads, then builds indexes — indexes last,
because bulk-inserting into an already-indexed table is far slower. `setup.ps1` does that order.

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

Postgres 17 with pgvector holds everything — rows, full-text and vectors in one database, no
separate search service. DeepSeek does the enrichment and the agent's reasoning. Embeddings are
bge-m3 over a hosted API, both for documents and for queries, so there is no model weight on the
server at all.

## Decisions

The judgement calls are the part worth reading, and they are written up properly in
**[DECISIONS.md](DECISIONS.md)** — the stemming bug that made "liquidation" match chemical notices,
why the query router is deliberately dumb, why the agent's tools return headlines instead of full
text, why the round cap is a cost ceiling. The short version of the ones that shaped it most:

- **Search demands adjacent words.** The looser version matched words borrowed from three different
  companies inside one bulk-removal list and confidently named the wrong company. Telling someone
  their supplier is in liquidation when it isn't costs far more than making them retype a name.
- **The trigram typo-tolerance was deleted.** Measured against the real data, no threshold separated
  its rescues from its false positives — "Bay Plumbing Limited" scored higher against HOULAHAN
  PLUMBING LIMITED than a genuine near-miss did against its real match.
- **Relevance picks the results, date orders them.** Two stages, not one. Sorting by date in the same
  query silently discards relevance entirely on the semantic route, because nothing in the `WHERE`
  clause depends on the query there.
- **The backend owns every limit.** The model asks; the code decides how much gets fetched.
- **Rate limits on anything that costs money**, counted in Redis so they hold across workers.

## What is not done

- **Location is best-effort.** There is no region column — place names live loose in the notice text
  — so "near me" is a search term, not a real filter. Region enrichment is the highest-value thing
  to add next.
- **No accounts, no watchlists.** You cannot ask it to tell you when something new is filed against
  a name, which is the obvious next feature and the reason to come back.
- **Evaluation is by inspection.** I verified search and agent quality by hand against the live
  database. There is a regression probe (`app/tests/search_probe.py`) but no real eval harness.
- **No bot check on the Ask button.** Cloudflare sits in front of the API, but a Turnstile check on
  the expensive route is still worth adding.

Data is from the New Zealand Gazette via DigitalNZ, CC BY 3.0 NZ.
