# Engineering decisions

A log of the non-obvious calls made building Fine Print, and the reasoning behind each. Every
tradeoff below was chosen against a real alternative — this is the record of *why the system is
shaped the way it is*, not just what it does.

---

## Retrieval

### Full-text uses the `simple` config, not `english`
**Problem:** Postgres's `english` text-search config stems aggressively. "liquidation",
"liquidator", "liquidating" — and the unrelated chemical word "liquid" — all collapse to the single
stem `liquid`. A search for "liquidation" was returning EPA hazardous-substance notices ("flammable
liquid containing…"), because they share the stem. Verified directly: `to_tsvector('english',
'liquidation')` = `'liquid'`.

**Decision:** Switched the generated `search_vector` column and every query to the `simple` config —
whole-word matching, no stemming. "liquidation" now matches only "liquidation".

**Tradeoff accepted:** We also lose *useful* stemming (director ≠ directors). For a corpus of
company names and legal terms, exactness is worth more than morphological recall — and returning
fewer, correct results beats more, wrong ones.

### Query routing is word-count only — rejected two "smarter" designs
**Problem:** deciding whether a query is a keyword lookup ("Sacred Hill") or a natural-language
question ("a wine business placed into receivership") that needs the LLM+semantic path.

**Considered and rejected:**
- A hand-maintained stopword/marker list — the original approach. Rejected as overengineering: it's
  an incomplete blocklist that misses any synonym nobody thought to add.
- A spaCy part-of-speech check (route to semantic if a verb is present) — smarter, but adds a model
  dependency, and still misfires on verbless noun-phrase descriptions common in legal notices.
- A tiny local LLM classifier (Qwen-0.5B via Ollama) — most accurate, but adds a network hop and a
  deployed model to every query, to fix a minority of ambiguous cases.

**Decision:** just `len(words) > 4`. A misrouted short query still searches correctly on the keyword
side (whole-word match + a typo fallback), so the failure cost is near-zero — which is what makes
the extra machinery not worth it. The simplest thing that survives its own failure mode wins.

### Typo tolerance is a scoped fallback, not a general fuzzy search
Trigram (`pg_trgm`) matching is indexed on `title` only, fires only when full-text returns nothing,
requires every query word to match (AND), and only considers short titles. Each constraint maps to a
measured failure: trigram on long text returns thousands of loose candidates and dilutes to noise
(measured 1,227ms, 81k candidates rechecked). It's deliberately kept small — it earns its place on
exactly one case (a misspelled short company name) and stays inert otherwise.

### Semantic search: fully hosted embeddings, zero model weight on the server
Both documents and queries are embedded through the same hosted API (bge-m3, 1024-dim). Because both
sides call the identical endpoint, they are guaranteed to occupy the same vector space by
construction — there is no local/hosted drift to verify and nothing to host. The server holds no
model weights, which matters because the target deployment has ~2GB of RAM.

### Chasing a 21s search down to 3.5s — by measuring, not guessing
Semantic queries took 21s. The instinct was to parallelise the two API calls; that was **wrong** —
the embedding input *is* the parser's output, so they are strictly chained. Timing each leg
separately found the real costs: parse 2.8s, embed 10.8s, vector SQL ~7s.

**The vector SQL:** there was no index on the embedding column at all, so every query sequentially
scanned all 205k vectors. An HNSW index (a proximity graph — vectors have no total order, so a
B-tree cannot apply) took it to **27ms**, confirmed by `EXPLAIN ANALYZE`.

**The embedding call:** 10.8s for one short string is absurd, so we isolated it. Not the SDK — raw
HTTP was equally slow. Not model size — bge-m3 is *larger* (568M vs 335M) and 33x faster. Testing
every embedding model on the same endpoint and key showed `bge-large-en-v1.5` at a **13.53s median
while every alternative ran ~0.4s**. It is served by exactly one provider with no fallback and
behaved like a single starved replica: 0.48s cold, 12-15s under sustained use.

Switching to bge-m3 also fixed a **quality bug nobody had noticed**: bge-large caps context at 512
tokens, so long notices were being silently truncated before embedding. bge-m3 allows 8192, at the
same price and the same 1024 dimensions. It was audited before committing — batch API, unit-norm
vectors, and 5/5 known-relevant notices ranked top-5 on real data — then all 205,246 notices were
re-embedded (~33 min, ~$0.51). Result: **21.1s → 3.5s**, now dominated by the LLM parse.

---

## The agentic layer

### Compact-by-default, drill-on-demand — the core tool design
The agent's search tool returns only `{id, headline, date, category, significance}` — never the full
notice text. Full text comes from a separate `get_notice` call, one notice at a time. **Why:** a
single Gazette strike-off notice can list 400 companies in its body. Letting the agent pull full text
freely would blow the context window on one query. The split forces cheap wide scanning first, then
expensive reads only on the few notices that matter — which is also how a human researcher works.

### The backend owns every resource limit, never the model
Tools take a query and filters; they do **not** let the model decide how many rows to fetch. All
caps (search size, history length) are backend constants. The model asks *what*; the backend decides
*how much*. This keeps a runaway or adversarial model from requesting unbounded data.

### A round cap as a cost ceiling, not a feature
The agent loops up to 6 tool-calling rounds. Most questions finish in 3-4; the cap only bites a stuck
loop. **Why it matters here specifically:** every round is a paid LLM call on our key, so the cap is
the per-question cost ceiling. At the limit the agent stops and answers with what it has — it degrades
gracefully rather than erroring or spending without bound.

### The prompt never exposes system internals
The agent narrates its work in plain language ("let me look through the record…") but is instructed
never to name a tool, a table, a field, or a score. To the user it's "the public record," not the
plumbing. This is a product decision (trust, polish) enforced at the prompt layer and verified in
testing — no leakage in either the serious or casual test run.

### Tone adapts to the user's register
One prompt, two voices: playful and dry for casual questions ("anything funny happen in
Christchurch?"), precise and professional the moment stakes appear (a contract, money, a worried
user). The agent reads the question and matches it — and is explicitly barred from joking about a
real insolvency to someone who sounds anxious.

---

## Data pipeline

### Year-window pull to work around a broken API
The DigitalNZ source API has no bulk export, and its date-sort is broken past a certain depth. Rather
than fight it, the pull walks the archive in year-sized windows with a byte-level checkpoint, making
the 205k-record pull forward-only and resumable after any interruption.

### Enrichment runs on DeepSeek, not Claude — a deliberate cost call
Structuring all 205k notices (headline, plain-English decode, category, significance) is an LLM job.
DeepSeek-v4-flash did it for ~$22 total — cheaper than the equivalent Claude run — with reasoning
disabled since it's extraction, not analysis. A conscious price/quality tradeoff for a bulk offline
job. (The *agent*, by contrast, runs reasoning-on, because there the multi-step planning is the point.)

---

### Rate limiting: defending against "denial of wallet"
The paid routes (semantic search, `/ask`) each cost real money in LLM calls, and an open POST endpoint
is a standing invitation to a bot that loops it and runs up the bill — or uses it as a free LLM proxy.
So the API runs two uvicorn workers behind a small Redis service that holds shared counters: per-IP
limits (10/min, 100/day → 429) and a whole-service daily budget (500/day → 503), which caps the
worst-case spend regardless of who is calling. Counters live in Redis, not process memory, precisely
*because* there are two workers — each has its own memory, so an in-process counter would silently
enforce double the limit. The limiter fails **open**: if Redis is unreachable it allows the request
rather than take the API down.

Backpressure is separate from rate limiting and easy to get wrong: FastAPI's thread queue does not
reject when full, it waits — so a flood piles up invisibly. The fix is uvicorn's `--limit-concurrency`
(off by default), which returns a clean 503 past a set number of concurrent requests. The agent route
adds its own non-blocking concurrency cap so a burst gets an instant "the desk is busy" instead of a
30-second wait behind others. Every layer sets `Retry-After`, and the frontend shows the exact wait.

## Known gaps (called out honestly)

- **Location is best-effort.** There is no structured `region` column — location lives unstructured
  in notice text — so "what's happening in my city" matches a place name as a search term, not a
  real filter. The highest-value next data addition is region enrichment + backfill.
- **App-side abuse protection is in; the edge layer is not.** Per-IP + global rate limits and a
  concurrency cap now guard the paid routes (above). Still recommended before a wide public launch:
  an edge proxy (Cloudflare) and a bot check (Turnstile) on the Ask button, which stop traffic before
  it reaches the server at all.
- **Evaluation is manual.** Search and agent quality were verified by inspection against the live
  database, not yet by an automated eval harness.
