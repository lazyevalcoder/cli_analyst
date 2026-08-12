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

## Design decisions (owner-confirmed 2026-08)

- **Insight layer** = structured What→Why notes + a Summary tab (see Stage B). Not a random linear narrative.
- **Dimension guardrail** applies to scorecard/breakdown columns: person/entity-level columns ineligible; prefer high-level controllable dimensions with ≤6 members (Region / Product Category / Segment / Ship Mode).
- **Overall-row trend** committed: last-N-period series on the Overall row only (all rows exist, so no 2-point fabrication); member cells stay current/prior.
- **Metric policy** — no single-dimension-member KPIs; no analyst-only statistical indices. Enforced in the O2 validator + blueprint pass; see `roadmap.md`.
- **No health status**; **no charting** (2-period proof, deliberately not PowerBI).

## Staged plan (canonical)

**Stage A — data + rendering, no LLM, low risk**
1. Tooltips = **definition + basis**: include `measurement` + `basis` + per-member `current`/`prior` in the payload.
2. **Unit normalization**: fractional-change (percent/ratio/pp → `%`) vs raw (count/currency/days → value + unit).
3. Show `executive_questions` under each section header — the matrix becomes an answering-board.
4. Deterministic per-section **callout** line: fastest driver + laggard + missing-data count.
5. **Dimension guardrail** — tighten `suggest_breakdown_dimensions` candidates (`builder.py`): drop person/entity-level columns; ≤6 members.
6. **Overall-row trend** — last-N-period series from the full `df` for the Overall row only; skipped/inapplicable metrics collapse to a compact footnote instead of a row.
7. **Headline strip** — deterministic one-line period summary (fastest mover / laggard), no LLM.

**Stage B — cached narrative + answering-board** (depends on Stage A)
8. Replace `interpret_priority`'s freeform narrative with **structured "What happened → Why" bullets** (per KPI: value + delta, driver, OFF flag, not-computable reason); cache per priority; render as a right-side notes rail per section.
9. **Summary tab** — one table per scorecard: Question | Indicator | Callouts (rows = executive questions).

**Park (confirm first)**
10. Cell-level "Ask why" drill-down via agentic deep-dive (the roadmap's `scorecard analyze`).

## Open questions

- **"Ask about this cell"** — include now (runs the analysis) or defer?
- **Compute cell granularity** for multi-dimensional outcomes: per-dimension members + overall (starting point) vs cross-dimension combos (Region × Category) as a later enhancement.