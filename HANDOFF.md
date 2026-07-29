# Fine Print — NZ Gazette accountability agent · HANDOFF

> **One line:** an agent that reads the NZ Gazette — the official record where the government is
> *legally required* to disclose things but writes them so no one ever reads them — makes it
> findable and readable, and flags the buried notices that actually matter.

**Status (2026-07-13):** concept + core positioning locked (§0). **Pull → load → index pipeline is
built and running end-to-end** (§4): 205,246 real notices sitting in Postgres, indexed, search-tested
with real queries. Not yet built: AI enrichment (plain-English decode, buried-lede score), embeddings,
the FastAPI endpoints, any frontend.
**Replaces:** Mailbin as the flagship portfolio project (Mailbin stays on the CV until this proves out).
**Why a portfolio project:** must be (a) technically impressive — a real agentic pipeline, not a 2-hour
vibe-code — and (b) built on a genuine insight, not a clone. Real users are a bonus, not the bar.

---

## 0. North Star — the core (the lore) 🧭

> **The site is not a "notice collection." It is a watch on *your interests* in the public record.**
> Notices are just the raw material.

**Core, named exactly:** *an **early-warning radar for your interests in the public record**.*
Consumer framing: **"a credit-check — but for everything the government officially records about
you and what you own."** The flagship interaction is **self-lookup ("Know yourself"):** you type your
name / your company → we tell you, in plain English (with citations), every official notice about you.

**The core is a *question*, not a pile of data.** Every notice type — a company dying, land being taken,
a charity closing — answers the *same one user question:*
> **"Did the official record just do something to what's mine?"**

**"What's yours" = a bundle of three (this is the audience spine):**
| | Plain meaning | Example notice |
|---|---|---|
| 💰 **Money** | what you're owed / invested / paid | a debtor company being liquidated |
| 🏠 **Property** | land, title, assets | government taking your road frontage |
| 🪪 **Name / standing** | your company, reputation, rights, membership | your business struck off the register |

The legal word that bundles all three is **"your interests."** That is the core noun.

### Decisions that fall out of this (do not re-argue)
1. **Killed the false binary.** "Complete govt-notice collection" *and* "all-round big-decisions
   collector" are **both weak as a core.** The first fights the official Gazette on its own turf
   (data completeness — we lose, it IS the source) and true completeness is impossible anyway. The
   second can't be self-relevant and the completeness problem bites hardest there. **Core = neither;
   core = "Know yourself" over a complete-by-design slice.**
2. **Self-relevance and completeness stop fighting** the moment we scope to notice types where the
   Gazette *is* the whole truth (Tier 1, esp. the insolvency cluster). Completeness becomes **free** —
   we never promise it, we just *have* it, because we deliberately fish only in the pond that's full.
3. **Reframed "completeness isn't our responsibility."** Right instinct, dangerous wording. We do NOT
   shrug at gaps on notices we show — that leaks trust, and **trust is the whole product.** Instead:
   **we only pick notice types that are complete by design, so the question never comes up.** For
   topics we don't fully cover (land, charities) we either don't show them in v1, or say honestly
   *"complete for X; for land the fuller record is at LINZ."* That one honest sentence **wins** trust.
4. **Engine vs spotlight.** The **"Know yourself" search is the engine** (self-interest = the most
   reliable motive on earth). The **buried-lede "Quietly filed this week" feed is a spotlight feature
   riding on top** — not the core.
5. **The core is SCOPE-INDEPENDENT.** Whether we ship only the Gazette insolvency cluster or later go
   "all the way" with LINZ + Charities Register + Companies Office, the core sentence *never changes* —
   we just widen the pond. So we **start narrow and grow without ever re-naming the product.**
   - *Vision:* "your interests, fully." *v1:* **"your money, via the Gazette, completely."**
   - Multi-source (LINZ/Charities/Companies Office) stays **Phase 3** — each new source is a separate
     scraper + format + re-opens the completeness-honesty burden on a new topic. Depth now, breadth later.

### The 27 notice types, folded into 5 human buckets (audience map)
| Bucket | Codes | Who cares | Complete on Gazette alone? |
|---|---|---|---|
| 🔴 **1. A business is dying/dead** (money) | `aw aa al ar ba cb md ds vw` | creditors, suppliers, employees, lawyers, competitors — *protecting their money* | ✅ **Yes** (gazetting IS the act) |
| 🏛️ **2. Government made/changed a rule** | `sl vr ps go au` (+ inactive `dl rs pb`) | lawyers, journalists, councillors, affected industry | ✅ Mostly |
| 🏞️ **3. Land / property** | `ln lt` | homeowners, neighbours, buyers, iwi, developers (*few per notice, each cares a lot*) | ⚠️ No → full record at **LINZ** |
| 🤝 **4. Organisation status changed** | `ct is fs pn` | members, donors, the org itself | ⚠️ No → **Charities Register / Companies Office** |
| 🗃️ **5. Grab-bag** | `gn gs ot` (+ inactive `cu`) | nobody specific | ❌ Partial — never promise |

**v1 lives entirely in Bucket 1** — strongest motive (*"is someone who owes me money going broke?"*)
**and** the one bucket where the Gazette is the whole truth, so we never apologise for a gap.

---

## 1. The product thesis (what we decided, and why)

We pressure-tested the idea hard. The conclusions that survived:

- **NOT a mass-consumer daily-news site.** Nobody reads the raw Gazette for fun — newspapers already
  filter the world for "interesting." We lose that fight. *Killed this framing.*
- **The Gazette's value is the opposite of a newspaper.** A newspaper is a *spotlight* on what's
  interesting to **many**. The Gazette is full of things critically important to a **few** people each
  (a land taking on your road, an exemption for your one competitor). Newspapers structurally can't
  serve that long tail — too few readers per item. **That gap is the demand.**
- **Three real users:**
  1. *"Does this affect me?"* — homeowner, supplier, small-biz owner searching one thing. **Pull.**
  2. *"Just tell me what got quietly decided."* — journalists, councillors, lawyers. **Push (alerts + buried-lede feed).**
  3. *"Look me/my company up."* — self-monitoring. The strongest hook: self-interest is the most
     reliable reason anyone uses anything. Think **a credit-check, but for the public record.**
- **The official site is old, government-built, no incentive to be good.** We can't beat it on *data*
  (it IS the source) — we beat it on **findability, plain-English, self-relevance, and alerts.**
  That clunky UX is the front-end moat; the **buried-lede detector** is the smart-end moat.
- **Competitor:** PublicData NZ (publicdata.co.nz) does reactive search of follow-the-money data.
  It does **not** touch the Gazette, submissions, or *proactive flagging*. That's our white space.

### The trust / completeness rule (decided)
> The Gazette is complete for any event where **publishing in it IS the legal act** (skip it and the
> act is invalid). It has holes where it's just a courtesy copy of a register kept better elsewhere.

So we **scope v1 to notice types where the Gazette is authoritative**, and we are **transparent about
coverage** ("complete for X; for full company status also see Companies Office"). Honesty about limits
builds trust; pretending to be total destroys it. We are explicitly OK being a "low-cap" tool that
covers most cases well — not a 100%-of-everything aggregator. **Multi-source integration (LINZ,
Companies Office, Insolvency Register) is Phase 3, only after v1 works.**

### Completeness tiers (see `reference/notice_types.json` for per-code tiers)
- **Tier 1 — effectively complete (build here):** the insolvency/commercial cluster (liquidators,
  receivers, administrators, winding-up, bankruptcies, removals/strike-offs, cessation, meetings),
  plus Secondary Legislation, Vice-Regal, Parliamentary, Departmental.
- **Tier 2 — covers most, fuller register exists elsewhere:** Land Notices/Transfers (→ LINZ),
  Charitable Trusts (→ Charities Register), Incorporated Societies (→ Companies Office).
- **Tier 3 — partial / catch-all, never promise coverage:** General Notices, General Section, Other.

---

## 2. Gazette technical reference (verified 2026-06-29 by scraping the live site)

### Notice-type codes
Full machine-readable table: **`reference/notice_types.json`** (27 codes, with category, tier,
active flag, and the v1 cluster marked). Each code is a **2-letter value** that appears BOTH in the
search URL (`noticeType[]=al`) AND as the prefix of every notice id (`2026-al3495` → `al`), so the
type is recoverable from the id itself.

> **Correction to an earlier assumption:** `aa` = *Appointment/Release of Administrators*, and
> `au` = *Authorities/Other Agencies of State* (an earlier note had `aa` mislabeled). The scraped
> table is authoritative.

### URL / retrieve patterns
| Purpose | Pattern | Returns |
|---|---|---|
| **Search / list** | `GET /home/search?keyword=&year=&pageNumber={n}&noticeNumber=&dateStart={DD+Mon+YYYY}&dateEnd=&noticeType[]={code}&act=` | HTML, **100 results/page**, **hard cap 10,000 per query** (page 100 max) → window by date for big types |
| **Notice detail** | `GET /notice/id/{year}-{code}{num}` (e.g. `/notice/id/2026-al3495`) | HTML: structured fields + full body |
| **Notice PDF** | `GET /notice/id/{year}-{code}{num}/pdf` | PDF (citation/archive copy) |
| **Form** | `<form action="/home/search" method="GET">` | the search is a plain GET form — easy to drive |

Base host: `https://gazette.govt.nz`. Coverage: **all notices since 2000** (1993–99 not online).

### Data access — RESOLVED (spike done 2026-06-29)
- **Primary route = DigitalNZ API** (open JSON, **no API key needed**, CC-BY, commercial OK).
  Endpoint: `https://api.digitalnz.org/v3/records.json?and[primary_collection]=New+Zealand+Gazette`
  (params: `per_page`, `page`, `text=`, date filters). **205,001 Gazette records — the whole archive
  since 2000.** Verified it returns **`fulltext` = the complete notice body**, plus `title`,
  `dc_identifier` (= Notice Number, e.g. `2020-al4473` → type `al`), `collection_title` (type),
  `display_date`/`date`, `landing_url` (citation back to gazette.govt.nz), pre-tagged `subject[]`
  (free Act + location signals), `license`, `is_commercial_use`.
  **Confirmed for the insolvency cluster: `fulltext` contains both `Company Number:` and `NZBN:`
  inline** — so we regex out our entity-linking keys; no HTML scrape needed for the core pipeline.
  (Filter gotcha: `collection_title` is NOT a filterable field — use `text=` search or `subject`.)
- **Fallback only = direct HTML scrape** of `/notice/id/{id}` (+ `/pdf`). Use just to grab the PDF
  archive copy, or if a field is ever missing from DigitalNZ. Polite scraping rules still apply.
- **RSS is dead to us:** the Gazette's own RSS needs an emailed API key + 1 query/day. Ignore it;
  DigitalNZ is the open back door instead.

### What to pull (per notice)
| Field | Source | Use |
|---|---|---|
| Notice id (`2026-al3495`) | id | primary key (encodes year + type) |
| Publication date | detail | recency / alerts |
| Notice type (code + label) | id / detail | backbone filter |
| Act / legislation | detail | pro filtering |
| Title (entity name) | list / detail | "look me up" axis |
| **Company Number + NZBN** | detail body | **entity-linking key across notices over time** (the gift) |
| Full body text | detail | plain-English decode + buried-lede scoring |
| PDF link + source URL | detail | citation + CC BY attribution |

NZBN = New Zealand Business Number, the permanent unique company id — lets us reliably tie "this
company" across many notices even when the name string is messy. Regexed straight out of `fulltext`
(see `build_notice_row_from_record` in `Prep/pipeline/pull.py` for a real example).

### Ingest pipeline (DigitalNZ-primary) — PULL + LOAD + INDEX now built, see §4 for details
```
1. PULL       DigitalNZ API: per_page=100, page through EVERY year 2000-present, ALL 27 notice types
              (no bucketing at pull time — save everything raw, bucket later so nothing is thrown away)
              -> Prep/data/notices.jsonl: id, code, type, date, title, nzbn, company_number, fulltext,
                 landing_url, source. Resumable (byte-offset checkpoint), idempotent re-runs.
2. LOAD       Prep/pipeline/load.py: upsert every row into Postgres, keyed on notice id (NOT NZBN —
              NZBN is null pre-2013, unfit as a key; id is the one field every notice always has).
3. INDEX      full-text (GIN/tsvector) + fuzzy company-name (GIN/trigram) + hard-filter btrees
              (code, date, nzbn, company_number) — all built, all verified against real queries (§4).
4. ENRICH-AI  classify -> plain-English decode (cited) -> buried-lede significance score   [NOT BUILT]
5. EMBED      pgvector semantic layer, on top of the above, once enrichment exists          [NOT BUILT]
```
HTML scrape of `/home/search` (100/page, 10k cap) is a FALLBACK only — not used, DigitalNZ covers it all.
**Manners (required):** throttle (~1 req/sec), cache (never refetch), explicit User-Agent, respect
robots.txt, stamp every record `Source: New Zealand Gazette (CC BY 3.0 NZ)`. Mind privacy on personal
insolvency; never republish anything suppressed; present facts, never accusations.

---

## 3. MVP scope (surgical v1)

**Gazette-only. Insolvency/commercial cluster only** (the 9 `mvp_insolvency` codes in the JSON).
End-to-end vertical slice on that one cluster: ingest → decode → search/self-lookup → buried-lede
score → (Phase 2) alerts. Include a couple of Tier-2 land-taking examples just to show the buried-lede
detector's range — but don't promise coverage on them.

### Lookup facets (organize the UI/search by these)
`notice type` · `entity name (company/person)` · `date` · `Act` — all dense & trustworthy on the
Gazette alone for Tier 1. `location` (partial, land notices) and the computed `buried-lede score`
ride on top.

### UI direction (sketched, not final)
- **Hero = one natural-language search bar** ("Ask anything…"): user types a plain question, AI reads
  matching notices, answers in plain English **with citations**. This is the flagship.
- **"Quietly filed this week" strip** under it so the page isn't empty for no-query visitors.
- **"Make this about you"** optional panel (suburb / company / topics) saved to **browser
  localStorage — no login, no server-side user data.** Privacy-friendly + cheap. Powers self-lookup
  + alerts. *(Results-page design still to do.)*

### Stack — DECIDED, running locally in Docker (see §4)
- Frontend: React + Vite + TypeScript. **Not started.**
- Backend: **FastAPI** (decided over Django — better fit for a thin API over precomputed data).
  Skeleton only (`app/main.py`, one `/health` route) — real endpoints not built.
- Store: **PostgreSQL 17 + pgvector**, in Docker (`pgvector/pgvector:pg17` image). Full-text (GIN/
  tsvector) and fuzzy trigram search **built and verified**; vector column exists (`embedding
  vector(1024)`) but nothing populates it yet — semantic search is not built.
- Offline pipeline: plain Python scripts in `Prep/` (pull.py, load.py), containerized but currently
  run locally against the Dockerized DB. Scheduling mechanism (cron? GitHub Actions?) still undecided
  — not needed yet, the historical backfill is done; only future deltas need a schedule.
- LLM: **Claude Haiku 4.5** for cheap high-volume passes; **Claude Sonnet 5** for buried-lede
  reasoning. *(Confirm current model ids/pricing via the claude-api skill before building — these
  drift.)*
- Cost guard: rules pre-filter + recent-months window for MVP + hard daily spend cap + per-IP rate
  limit on any live "explain" endpoint. Heavy work offline (pay once); live stays light/cheap.

### Legal
NZ default license is **CC BY** (reuse incl. commercial, with attribution). Gazette = **CC BY 3.0 NZ**.
Official public record → low defamation risk. Cite every claim back to its source notice.

---

## 4. Infrastructure & data pipeline — current status (2026-07-13)

**Everything below is built, running, and verified against real data — not a plan.**

### Bring the stack up
```powershell
# Docker Desktop must be running first (tray whale icon steady) — `docker` CLI works without it,
# but `docker compose up` needs the actual engine, not just the installed binary.
cd C:\Users\PC\Desktop\Github\Gazette
docker compose up -d db          # starts Postgres only (app/prep build later, not needed yet)

# First time ever (fresh volume): table -> load 205k notices -> indexes, in that order
.\setup.ps1

# Already have data, just need to (re)apply schema/index changes:
.\Prep\db\apply.ps1                    # all files in Prep/db/init/
.\Prep\db\apply.ps1 -Pattern "02_*"    # just one file
```
Secrets live in root `.env` (POSTGRES_*, gitignored) and `Prep/.env` (DIGITALNZ_API_KEY, gitignored)
— `.env.example` in both places is the committed template. DB port is bound `127.0.0.1:5432:5432`
(localhost-only, safe to leave that way even on a public server).

### Why two `.sql`-apply paths exist
`Prep/db/init/*.sql` auto-runs **once**, only on a container's first-ever boot (empty volume) — that's
Postgres's own `docker-entrypoint-initdb.d` mechanism, mounted in `docker-compose.yml`. It does **not**
retroactively run on an already-initialized container — that's what `apply.ps1` is for (pipes the same
files into a running container by hand). Both point at the same files; nothing is duplicated.

### Current data state
- **205,246 rows** loaded into the `notices` table (upserted, keyed on notice `id` — see
  `Prep/db/init/01_schema.sql`). Pull is caught up through 2026, fully resumable for future deltas
  (`python -m pipeline.pull` from `Prep/`).
- Filled: `id, code, type, date, title, nzbn, company_number, fulltext, landing_url, source`.
- **Still NULL for every row:** `plain_english, significance_score, embedding` — these are the AI
  enrichment + vector stages, not built yet. That's the actual next milestone.

### Indexes — built, and load-tested against the real 205k rows
| Index | Type | Column(s) | Verified real query time |
|---|---|---|---|
| `notices_pkey` | btree | `id` | — (upsert key) |
| `notices_code_idx` | btree | `code` | 2ms combined with date range |
| `notices_date_idx` | btree | `date` | (combined above) |
| `notices_nzbn_idx` | btree | `nzbn` | **0.1ms** exact lookup |
| `notices_company_number_idx` | btree | `company_number` | **0.16ms** exact lookup |
| `notices_search_idx` | GIN / tsvector | generated `search_vector` (`title`+`fulltext`, stemmed) | **4.2ms** single-term, **27.7ms** combined with a hard filter |
| `notices_title_trgm_idx` | GIN / trigram | `title` | **1,227ms** on a typo query — see caveat below |

**Search-design conclusions (hard-won, don't re-derive):**
- **Hard filters** (`code`, `date`, `nzbn`, `company_number`) = exact/range btree lookups, sub-millisecond,
  the "gate" layer. Postgres combines multiple filters itself via `BitmapAnd` — proven live, no app-side
  logic needed to intersect them.
- **`search_vector`** (full-text) = the word-based "soft" layer. Auto-maintained generated column, no
  app code keeps it in sync. Handles stemming ("liquidate" matches "liquidating") for free.
- **Trigram (`%` similarity) is short-text-only** — proven with real queries: a long natural-language
  query describing a notice *conceptually*, without reusing its exact words, scored **0.05** (near-zero,
  would never match). Trigram measures raw character-chunk overlap of the *whole string*, not meaning —
  useful only for typo-tolerant lookup on short identifiers (a misspelled company name), not for
  anything sentence-shaped. That job needs either full-text (word-shaped queries) or **vectors**
  (meaning-shaped queries) — vectors are the still-missing piece for true semantic/long-query search.
- Trigram is also slow when the query contains common substrings (e.g. "Limited" appears in thousands
  of company names) — the index over-fetches candidates sharing *any* trigram, then rechecks exact
  similarity per row. Fine for occasional fuzzy lookups, not for a hot path.

### Operational scripts (don't hand-type these again)
- `setup.ps1` (repo root) — one-time full bring-up: table → load → indexes, in the perf-correct order
  (indexing an empty table then bulk-inserting is much slower than the reverse).
- `Prep/db/apply.ps1` — re-apply `Prep/db/init/*.sql` to an already-running container; `-Pattern` filters
  which files.
- `Prep/pipeline/pull.py` — resumable DigitalNZ pull, run from `Prep/`: `python -m pipeline.pull`.
- `Prep/pipeline/load.py` — jsonl → Postgres upsert, run from `Prep/`: `python -m pipeline.load`.

## 5. Open decisions / next steps
1. **AI enrichment** (offline batch): classify -> plain-English decode (cited) -> buried-lede
   significance score. Fills `plain_english` / `significance_score`. Model choice: Haiku for volume,
   Sonnet for the harder buried-lede judgment call (confirm current ids via claude-api skill first).
2. **Embeddings**: pick a model (Anthropic has no embeddings endpoint — Voyage AI or a local model),
   populate `embedding vector(1024)` (adjust the dimension to match whatever's chosen), build the
   pgvector index, wire into the query layer alongside the existing hard-filter + full-text combo.
3. **FastAPI real endpoints** — `app/main.py` is a placeholder (`/health` only). Needs the actual
   search/self-lookup endpoint once the query-parsing design (hard filter + soft signal fusion,
   already discussed) is ready to implement.
4. **Results page design** (the answer + cited notices + plain-English decode) — not started.

## 6. Repo layout
```
Gazette/
  HANDOFF.md                    <- this file (start here)
  docker-compose.yml            <- orchestrates db + app + prep (run from repo root)
  setup.ps1                     <- one-time fresh bring-up (table -> load -> indexes)
  .env / .env.example           <- Postgres credentials (compose reads these)

  app/                          <- live FastAPI service (reads the DB only). Skeleton only so far.
    Dockerfile  main.py  requirements.txt

  Prep/                         <- offline jobs: pull, load, db schema. Run on demand, not always-on.
    Dockerfile  requirements.txt  .env / .env.example   (DIGITALNZ_API_KEY)
    pipeline/pull.py            <- DigitalNZ -> Prep/data/notices.jsonl (resumable)
    pipeline/load.py            <- notices.jsonl -> Postgres (upsert)
    shared/config.py            <- env vars + paths, single source of truth
    shared/gazette.py           <- record-parsing helpers (id/date/text extraction)
    reference/notice_types.json <- the 27 notice-type codes + tiers (machine-readable)
    db/init/01_schema.sql       <- table + extensions (auto-runs on fresh container)
    db/init/02_indexes.sql      <- full-text/trigram/btree indexes (auto-runs on fresh container)
    db/apply.ps1                <- re-apply db/init/*.sql to an already-running container
    data/notices.jsonl          <- 205,246 pulled notices, gitignored (regenerate via pull.py)
```

## 7. Sources
- Find a notice (codes) — https://gazette.govt.nz/find-a-notice
- About — https://gazette.govt.nz/about-us  · Browse issues — https://gazette.govt.nz/issues
- DigitalNZ API — https://api.digitalnz.org/records.json?and[primary_collection]=New+Zealand+Gazette
- DigitalNZ developers — http://www.digitalnz.org/developers
- NZGOAL / CC BY — https://www.data.govt.nz/toolkit/policies/nzgoal/nzgoal-version-2
- Gazette open dataset (CC BY 3.0 NZ) — https://catalogue.data.govt.nz/dataset/new-zealand-gazette
- Competitor — https://publicdata.co.nz/
