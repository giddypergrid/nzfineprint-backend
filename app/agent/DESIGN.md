# Fine Print — Agentic Research (Part 2 design)

The single-shot `/search` answers "find me notices like X." It cannot answer the questions the
product actually exists for — "should I worry about this company", "what's happening near me",
"who's behind these failures". Those need **multiple retrievals, cross-referencing, and synthesis**.
That is the agent.

## The loop

```
user question
   -> agent (DeepSeek v4, reasoning ON) plans
   -> calls a tool (1 round-trip)
   -> reads compact result, decides next step  (may retry a tool with new params if unhappy)
   -> ... up to MAX_ROUNDS (6) ...
   -> synthesizes a plain-language answer
```

- **3-4 rounds is normal.** The chaining IS the value, not overhead.
- **The agent self-corrects.** Weak results -> it widens a date range / rephrases / tries a sibling
  term and calls again, on its own judgment. No scripted retry.
- **MAX_ROUNDS = 6** is a cost ceiling, not a target — every round is a paid LLM (+maybe embed)
  call on our keys. At the cap the agent stops and answers with what it has, gracefully.

## Tools (the real product decision)

Read-only, purpose-built, **compact-by-default / drill-on-demand**. The LLM never sees raw SQL,
never sets resource limits (backend owns those), never learns table/column names.

| Tool | In | Out | Job |
|---|---|---|---|
| `search_notices` | query, filters (category/action/date/significance), limit | list of {id, headline, date, category, significance} — **no fulltext** | wide cheap scan / fan-out |
| `get_notice` | id | one full notice (plain_english, fulltext, parties, url) | drill into the few that matter |
| `get_company_history` | nzbn / company_number / name | all notices for that entity, date-ordered, compact | the timeline primitive |
| `find_related_parties` | notice id / company | affected_parties + other notices naming them | the entity-linking hop |

Deliberately **out of v1**: `aggregate_notices` (group-by/ranking) — different use case (dashboards),
real added complexity. Basic due-diligence is find -> timeline -> detail -> connection.

## Worked example (all four, chained)

*"I'm about to sign a supply contract with Sacred Hill. Should I be worried?"*
1. `search_notices("Sacred Hill")` -> multiple distressed entities surface
2. `get_company_history("Sacred Hill Family Vineyards")` -> receivership 2021 -> liquidation 2023
3. `get_notice(<the receivership id>)` -> KordaMentha, ASB Bank, the detail
4. `find_related_parties(<that id>)` -> a director also tied to a separate 2019 liquidation
-> synthesis: "Yes, be cautious — 2-year decline, and a director has a prior failure."

## Behavior rules (the prompt's job)

1. **Narrated plain-language steps.** Emit user-facing progress ("Looking for Sacred Hill records…
   found 3, tracing the timeline… checking who else is connected"). Shows we did the work during
   the wait. **Never** names a tool, table, column, score, or any system internal.
2. **Always give the closest answer + honest hedge.** Never a bare "nothing found." If the data is
   thin (e.g. no location field for "Christchurch"), return the best hit and flag it: "I couldn't
   find records specifically tied to Christchurch, but here's what mentions it recently…"
3. **Agent owns interpretation.** "recent" -> a concrete date bound. "funny/notable" -> high
   significance. Fuzzy human -> concrete filter is the agent's job.
4. **Tone adapts to the user's register.** Casual/playful question -> quirky, dry-humoured, light.
   Serious question (contracts, risk, money, legal) -> straight, precise, professional. Read the
   question, match it. Never joke about someone's insolvency to a person who sounds worried.
5. **Never disclose system structure.** No tool names, no "the database", no field names, no
   "significance_score", no vector/embedding talk. To the user it's just "the public record".

## Data gap inherited by the agent (honest)

Accuracy tracks which fields are structured. `date`, `event_category`, `action_taken`,
`significance_score`, entity ids = first-class. **Location is not** — no `region` column, it lives
unstructured in fulltext. "What's happening in my city" therefore lands on best-effort fulltext
matching. The toolset is sound; the data has one known gap. Closing it = add `region` to enrichment
+ backfill (cheap, region-only pass). Deferred for v1, flagged so the agent hedges location.
