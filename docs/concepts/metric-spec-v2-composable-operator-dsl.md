# Metric Spec v2 — Composable Operator DSL (Reliability Ladder)

A design note for making priority-metric computation a *developer product* rather than a growing list of one-off fixes. Current compute (`priority_spec_prompt.md` + `build_metric_script`) expresses only single-step aggregates (`count|sum|mean|std|ratio|share|topk_share`). A real run on Pipeline Analytics pre-filtered **15 of 24** metrics as "non-scalar" — but nearly all are expressible as *composition* (group → per-group value → outer aggregate), the DAX/PowerBI iterator pattern. This note proposes the general fix: a closed, curated **operator DSL** + a **reliability ladder** (deterministic template → restricted expressions → sandbox escape hatch).

**Status:** implemented 2026-08-02 on `feature/priority-compute-tiers`. This note is the design + detailed plan; the code, prompt, and tests land it. **Real-model verification (2026-08-02):** `compute 1` on Pipeline Analytics landed **11/24 computed** — the "~14/15 previously-inexpressible metrics now computable" claim holds only where the *data grain* supports the measurement; the residual not-computable metrics are data-limited (stage transitions / per-stage timing need timestamps the CSV lacks), not DSL gaps. `analyze 1` / `interpret 1` pending.

---

## Why the current schema is a wall, not a language

`{name, agg, value_column, condition?, numerator/denominator, compare, unit}` forces every metric through ONE aggregate step. Anything needing two steps is unrepresentable:

- *"Average count per agent"* = group by `sales_agent` → count → **then** average those counts.
- *"First-time accounts"* = a cross-period membership test (row with no prior occurrence).
- *"Top 20% accounts"* = percentile cut, not integer `k`.

The pre-filter (`_non_scalar_reason`) catches these by keyword and marks them `not_computable`. That was the correct *honest* interim behavior — but as a product, "we can't express it" must map to "the DSL needs one more operator," not "go away." And the sandbox already exists; the real constraint was never *capability*, it was *reliability of LLM-written pandas*.

---

## The reliability ladder (the actual product shape)

| Level | Mechanism | Reliability | Coverage | Who writes it |
|---|---|---|---|---|
| L1 | **Operator DSL** — composed spec → deterministic template | 100% deterministic, auditable, unit-testable | ~80% of metric shapes | LLM composes; devs read/override |
| L2 | **Restricted expressions** — derived columns, conditions; AST-validated, no statements/imports | High (sandbox AST checks) | adds arithmetic + date transforms | LLM writes *expressions*, not code |
| L3 | **Sandbox escape hatch** — `kind: "custom"`, sandboxed pandas | LLM-assisted, human-reviewed | **anything** | developer/LLM, reviewed |

**Guarantee:** if the DSL can't express a metric, the developer writes it in the sandbox. The product never hits a hard wall, and the common case stays fast + reproducible. The current `sandbox.py` (AST checks, blocked substrings, subprocess isolation, timeout) already provides L2/L3 safety.

---

## Operator catalog v1 (closed, curated, tested)

Each operator is a pure function over `(df, period)` → scalar or vector, compiled by the template. The set is deliberately small and versioned; adding one is a reviewed, tested event (see *Governance*).

### Aggregate (existing, retained)
`count`, `sum`, `mean`, `std`, `ratio` (num/denom), `share` (num as share of denom), `topk_share`.

### Derive — L2 restricted expressions (new)
Adds a column to the per-EQ `prep` namespace before metrics consume it:

| op | params | example |
|---|---|---|
| `derive.days_between` | `start`, `end`, `as` | `{op:"derive.days_between", start:"engage_date", end:"close_date", as:"cycle_days"}` |
| `derive.year_of` | `column`, `as` | quarter-of / month-of analogues |
| `derive.month_of` | `column`, `as` | — |
| `derive.arithmetic` | `expr` (AST-validated expression over column names; no statements, no imports, no `open(`/`eval`/`exec`) | `{op:"derive.arithmetic", expr:"close_value / qty", as:"avg_price"}` |

### Group + iterate — the DAX iterator (new, the key unlock)
Collapses a per-group vector back to ONE scalar:

`group_by(column) + inner_agg(count|sum|mean|std|min|max) over value` then `outer_agg(mean|std|max|min|sum)`.

- `AVERAGEX(VALUES(sales_agent), COUNTROWS(sales))` → `group_by: "sales_agent", inner_agg: "count", outer_agg: "mean"`
- `STDEVX.P(VALUES(sales_agent), [WinRate])` → `group_by: "sales_agent", inner_agg: "mean", value: "win_flag", outer_agg: "std"`
- `MAXX(VALUES(product), [ProductShare])` → `group_by: "product", inner_agg: "share", ... , outer_agg: "max"`

### Window / cross-period — membership primitives (new)
| op | meaning | example |
|---|---|---|
| `count_distinct` | distinct count of `value_column` in the period | active accounts |
| `new` | count of `value_column` whose **first occurrence** is in the current period (no prior-period row) | first-time accounts, new agents |

Implementation: `new` = distinct `value_column` present in current-period rows minus distinct values present in any prior-period row (needs the full date range, not just `prior_start..prior_end`).

### Percentile (new)
`topk_share` `k` accepts a **fraction** `0 < k ≤ 1` → top-`k`% members by `value_column`. `k=0.2` = top 20% of accounts by share.

---

## Spec v2 — composition is native

Back-compatible: a spec with no `prep`/`steps` behaves exactly like today (single aggregate + compare).

```json
{
  "name": "Time-in-Stage Velocity",
  "prep": [
    { "op": "derive.days_between", "start": "engage_date", "end": "close_date", "as": "cycle_days" }
  ],
  "steps": [
    { "op": "group", "group_by": "deal_stage", "inner_agg": "mean", "value": "cycle_days", "outer_agg": "mean" }
  ],
  "compare": "pct_change",
  "unit": "days"
}
```

```json
{
  "name": "New Account Acquisition Rate",
  "steps": [
    { "op": "new", "value_column": "account" }
  ],
  "denominator": { "agg": "count_distinct", "value_column": "account" },
  "compare": "pct_change",
  "unit": "ratio"
}
```

- `prep` columns are computed once per executive question and shared by all metrics in that EQ — this is "multiple measures, then do the calc": a later metric can reference an earlier metric's `prep` output.
- A metric may also reference *another metric's* recorded value as an input (`input_ref`) — compose measures from measures (see *Composition rules*).

### Template changes (`build_metric_script`)
- Split into two phases: (1) emit `prep` column-derivation code guarded by try/except, once per EQ; (2) emit per-metric value computation using the existing per-metric try/except pattern.
- `group + outer_agg` emits: `_g = df.groupby(col)[value].agg(inner) ; _v = _g.agg(outer)`.
- `new` emits a membership query over the full date range.
- Fractional `k` emits a rank-and-take-top-`k%` block.
- Keep the single `print(json.dumps(_out))` contract; `_parse_compute_output` is unchanged.

### Validator changes (`_validate_spec`)
- Validate operator names against the catalog; validate `group_by`/`value` are real schema columns **or** `prep`-derived names; validate `outer_agg`/`inner_agg` enums; validate fractional `k ∈ (0,1]` for topk_share; compile-check L2 `expr` via AST (reuse `sandbox._check_ast_safe`).
- `prep` op output names must not collide with real columns; a metric may only reference `prep` outputs declared *earlier* in its own spec or in the EQ's shared prep.

### Pre-filter becomes a classifier with a reason, not a wall
`_non_scalar_reason` stays, but its output gains structure: `not_computable` records carry a machine-readable `missing_primitive` field (e.g. `"group.outer_agg"`, `"distinct_window"`, `"requires stage-entry timestamps"`). This turns `not_computable` into the **operator backlog** — developers see exactly which primitive to add or which data grain to provide.

---

## How the 15 pre-filtered metrics map onto v2

| Metric | Current status | v2 expression |
|---|---|---|
| Sales Agent Capacity Utilization | not_computable | group_by `sales_agent` count, outer `mean`, pct_change |
| Engagement Frequency Momentum | not_computable | group_by `account`×`month`, outer `mean` (needs `derive.month_of`) |
| Time-in-Stage Velocity | not_computable | **relabel → "Cycle Time by Stage"**: derive `cycle_days`, group_by `deal_stage`, outer `mean` (Won/Lost only; open stages have null close_date) |
| Account Engagement Intensity | not_computable | group_by `account`, outer `mean` |
| Product Complexity Index | not_computable | group_by `product`, inner share, outer `max` or topk |
| Sales Agent Win Momentum | not_computable | group_by `sales_agent`, inner ratio, outer `mean` |
| Stage Attrition Rate | not_computable | group_by `deal_stage`, inner ratio, outer `max` (or overall rate) |
| Account Concentration Risk | not_computable | topk_share `k:0.2` |
| Product Fit Mismatch | not_computable | group_by `product`, inner ratio, outer `max` deviation |
| Sales Agent Turnover Impact | not_computable | `new` on `sales_agent` |
| Deal Size Variance | not_computable | group_by `deal_stage`, inner `std`, outer `max` |
| Product Yield Shift | not_computable | group_by `product`, inner share, outer `max` |
| Account Yield Shift | not_computable | group_by `account`, inner share, outer `max` |
| Sales Agent Yield Variance | not_computable | group_by `sales_agent`, inner ratio, outer `std` |
| New Account Acquisition Rate | not_computable | `new` on `account` |

Net effect: **~14 of 15 become computable**; only Time-in-Stage keeps a caveat (relabeled + limited to closed stages). The pre-filter's `missing_primitive` for the residual cases feeds the operator backlog.

---

## Sequencing

1. **L1 core — group/outer_agg.** Add `group_by` + `inner_agg` + `outer_agg` to `_validate_spec` and `build_metric_script`. Tests: mean-of-counts, std-of-ratios, max-of-shares; verify against the 15 metrics.
2. **L2 derive.** Add `derive.days_between`, `year_of`, `month_of`, `arithmetic` (AST-validated). Tests: `cycle_days` on Pipeline Analytics; arithmetic over real columns.
3. **Window + percentile.** Add `count_distinct`, `new`, fractional `topk_share` `k`. Tests: first-time accounts on a seeded df; top-20% on Pipeline Analytics.
4. **L3 escape hatch.** `kind: "custom"` — spec carries a `code` block run through `sandbox.execute_code` (existing guards), value registered like any other; mark `source: "custom"`. Tests: sandbox blocks `import os`; a custom spec returns a value.
5. **Composition of measures.** `input_ref` so one metric consumes another metric's recorded value; `prep` shared per EQ.
6. **`missing_primitive` + backlog.** `_non_scalar_reason` returns a structured reason; `not_computable` records carry `missing_primitive`; `priorities compute` summary prints a "new primitives suggested" line.
7. **Prompt update.** `priority_spec_prompt.md` documents the operator catalog + examples; a few-shot of composed specs anchored. Re-verify `compute 1` on Pipeline Analytics (expect ~23/24 computed).

---

## Governance

- **Adding an operator is a reviewed event**: catalog + template emission + validator + ≥2 tests, in one commit. The catalog is the contract — documented in this file and echoed in the prompt.
- **Precedence:** validator (L1/L2) > sandbox (L3). A metric that can be expressed at a lower level must not silently use a higher one (auditability).
- **Naming honesty:** if a metric's authored name overclaims what the grain supports (Time-in-Stage vs Cycle Time), the compute summary flags it for relabel rather than computing a mismatched number.

---

## Open questions (deferred)

- **Multi-grain composition** (account × month) — whether `group_by` accepts a list (syntactic sugar) or requires a `prep` derive to materialize a composite key. Start with a single `group_by` column; a composite key is a `derive` output.
- **Percentile tie-breaking** for fractional `topk_share` — deterministic order required; default: sort by `value_column` desc, stable.
- **`new` over partial data** — if the dataset's earliest date falls inside the "current" period (no prior history), `new` degenerates to `count_distinct`; document this behavior rather than failing.

---

## Related docs

- `priority-compute-analyze-three-tier-split.md` — the three-tier compute/analyze/interpret model this extends.
- `roadmap.md` — "Compute tier performance" (spec + template) and Phase 0 (O2/O3 priorities-quality), the eventual source-quality fix.
- `Executive Scorecard Product Concept.md` / `Executive dashboard design framework.md` — the scorecard the operator DSL ultimately feeds.
