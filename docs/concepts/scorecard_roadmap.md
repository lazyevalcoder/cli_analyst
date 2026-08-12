# Scorecard Roadmap — End-User Scorecard Improvements

Reference project: **SalesOrders** (the clean scorecard). Wear a RevOps manager hat when reviewing.

## Where we are

We ship a read-only scorecard page (`/scorecard` via the local viewer) that renders the pre-computed matrix from `priority_values.json`:

- **Sections** = priorities (in file order), titled like a P&L review.
- **Rows** = KPI + supporting metrics (Goal-ordered; KPI bold, ops indented).
- **Columns** = "Overall" first, then the priority's breakdown-dimension members, so every member reads *against the company* (e.g. East +111% vs overall +49%).
- **Values** formatted by `unit` (percent/ratio/pp → `+48.7%`; days → `-0.1d`); `—` for not-computable with the stored reason in a cell tooltip.
- **No health status** — grid only by explicit decision (health was deferred to the reasoning layer).

## What's already good

- The grid answers the RevOps question in one screen: *member vs. company*, period framed up top ("Q4-2013 vs Q3-2013").
- `—` cells carry an honest, tooltip-visible reason (e.g. "no prior-period baseline — prior value is 0") — this is the trust layer; BI tools do not do this.
- Clean end-user surface: no schema/JSON/KG noise.

## What can be improved (no LLM needed)

| # | Gap | Fix |
|---|---|---|
| 1 | Every number has a `measurement` (definition) but it is not exposed. Tooltips show `basis` only. | Add `measurement` per metric → tooltip = definition + basis. Pure data plumbing. |
| 2 | "What moved fastest / weakest cell" requires scanning the whole grid. | Deterministic per-section **callout line**: fastest driver + laggard (no LLM). |
| 3 | The executives' questions are not shown even though they exist in `priorities.json`. | Render each priority's `executive_questions` under its section header — the matrix becomes an answering-board. |
| 4 | Mixed units look inconsistent (percent vs `d` vs raw). | Normalize presentation: two buckets — fractional-change (percent/ratio/pp → `%`) vs raw (count/currency/days → value + unit). |

## Where the dynamic-insight layer goes

We are **not** traditional BI (Tableau/PowerBI). We hold only 2 points per metric (current/prior), so **no sparklines / trend charts** — a chart would be fabricated from nothing. Our moat is a **narrative over a provable grid**.

Place insights in two tiers:

**Stage B — cached narrative (reuses the existing `interpret_priority` LLM engine)**
- A collapsible **"What the numbers say"** block directly under each section matrix:
  1. deterministic first line (fastest mover / laggard — no LLM),
  2. then a plain-language interpretation generated via the existing `interpret_priority` prompt.
- **Cache per priority** in a small per-project file, invalidated by the same `generated_at`/fingerprint gate that already exists. Add a "refresh" affordance.
- Zero new prompt work; reuses `interpret_priority_prompt.md`; cheap + auditable.

2. **Headline strip** at the top of the page ("This period: revenue +48.7% on AOV +82% despite volume -9.6%; East carried growth"). One or two sentences, deterministic or a cached LLM line.

## Parked (confirm before building)

- **Cell drill-down "Ask why"** — hover/click a cell → deep agentic `analyze` scoped to `(metric, member filter)`. This is the roadmap's `scorecard analyze`; the highest-moat click, and also the biggest lift.
- **Charting (multi-period time series)** — deliberately out of scope. We are a 2-period proof + story, not PowerBI.

## Staged plan

**Stage A (data + rendering, no LLM, low risk)**
1. Include `measurement` + `basis` + per-member `current`/`prior` in the payload; tooltips show definition + evidence.
2. Show `executive_questions` in each section header.
3. Deterministic per-section callout (fastest/laggard cells, missing-data count).

**Stage B (cached narrative)** — depends on Stage A.
4. Generate + cache a per-section "What the numbers say" via the existing `interpret_priority` prompt on demand; render as a collapsible insight card under each matrix.

**Park (confirm first)**
5. Cell-level "Ask why" drill-down via agentic deep-dive.

## Next session questions

1. Stage B on or off? (Adds a cached LLM call per priority; makes the scorecard "the thing that explains the grid".)
2. "Ask about this cell" — include now (runs the analysis) or defer?