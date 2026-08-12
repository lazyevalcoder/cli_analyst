# Scorecard Roadmap

Foundation work for turning the current priority output into a scorecard artifact (like a PowerBI/Tableau dashboard). No frontend yet — this lays the data/prompt/structure groundwork.

> **Related design note:** `docs/concepts/priority-compute-analyze-three-tier-split.md` proposes the `priorities compute / analyze (deep) / interpret (quick)` split. Its per-priority `compute` is the same engine as this roadmap's scorecard compute step (step 3 below), built per-priority and earlier. Implement that first — this roadmap consumes it.

## Vision

- Scorecard is the **data artifact** (a dashboard matrix): outcomes as sections, dimensions as columns, metric values computed per cell.
- Analysis is the **drill-down** on scorecard cells ("double-click" a cell → explain that slice) plus independent analysis.
- Briefing is the **narrative layer** on top of the scorecard: executive summary + detailed slides.
- This matches the docs' trust-layer principle: `Data → Scorecard → Pattern Detection → AI Explanation → Action` (not `Data → AI → Insight`).

## Gap analysis (current state)

| Piece | Exists today | Gap vs. vision |
|---|---|---|
| Outcome sections | `priorities.json` → 3 priorities, each with executive questions → KPI + supporting metrics | Priorities are unordered, un-typed, no narrative arc; no `type` (strategic/operational) |
| Dimension columns | Knowledge graph has `dimension` nodes (`location`, `category`, `segment`, `ship_mode`) but no edges to KPIs; `reasoning_context_prompt` already produces `key_personas` | Dimensions aren't tied to outcomes; nothing picks columns the way a RevOps/Finance/Supply Chain manager would |
| Computed cell values (like PowerBI/Tableau) | Nothing computes metric values | No data matrix exists at all |
| Briefing | `do_briefing` produces qualitative `priority_insights` + questions; `briefing.json` is `{}` in both projects | Not an "executive summary + detailed slides" artifact built on scorecard data |
| Analysis | `agentic_answer` (sandbox code-gen) is solid and reusable | No "double-click on a cell" entry point |

## Design decisions (confirmed with user)

- **Type classification:** whole scorecard only — one `type` field (`strategic` | `operational`); all outcomes share it.
- **Decide vs ask:** LLM auto-decides; asks the user via shell prompt only if unsure; user can override with `scorecard strategic|operational`.
- **Dimension columns:** LLM picks per outcome from KG dimension nodes, but prompt is written so the choice mirrors what a RevOps/Finance/Supply Chain manager would prioritize for the dataset.
- **Compute vs reuse:** scorecard is like a PowerBI/Tableau dashboard — compute fresh dimension-sliced metric cells. Insights/analysis are based on the scorecard data (double-click analysis) or independent analysis.
- **Briefing:** like an executive summary + detailed slides — the three outcomes'/priorities' summaries become the briefing.

## Proposed `scorecard.json` data model (persisted in `metadata/`)

```json
{
  "type": "strategic",
  "title": "...",
  "lens": "Finance Manager",
  "story": "Where are we → what drives it → where's the risk",
  "dimensions": ["Region", "Product Category"],
  "generated_at": "...",
  "outcomes": [
    {
      "title": "Revenue Growth & Market Momentum",
      "story_role": "Chapter 1 — Where are we?",
      "priority_ref": "Revenue Growth & Market Momentum",
      "dimensions": ["Region"],
      "kpis": [
        {
          "name": "...",
          "metric": "Sales",
          "ref": "<catalog-id>",
          "cells": [
            { "filters": {}, "value": 0.27 },
            { "filters": { "Region": "East" }, "value": 0.18 }
          ]
        }
      ],
      "supporting_metrics": [ "... same shape ..." ]
    }
  ]
}
```

Cells are filter-keyed so a frontend renders the matrix and a "double-click" targets `(outcome, metric, filters)`.

## Generation pipeline — `scorecard regenerate`

1. **Design (1 LLM call)** — `scorecard_prompt.md`: inputs = schema, unified KG, metric catalog, priorities, `key_personas`. LLM decides `type`, picks storytelling flow + ordered outcomes, and chooses dimension columns as the persona would. Returns `type` + `needs_confirmation`.
2. **Type confirmation** — if `needs_confirmation`, shell prompts `input()`; user can override anytime with `scorecard strategic` / `scorecard operational`.
3. **Compute (1 LLM call per outcome)** — `scorecard_compute_prompt.md`: LLM writes pandas code (guided by each metric's `measurement` formula) to produce the matrix and `print(json.dumps(cells))`; executed in a fresh sandbox namespace on a copy of `df` (timeout enforced); output parsed back into `cells`.
4. **Persist** `scorecard.json`.

## Shell surface

- `scorecard` — text-render the matrix (sections = outcomes, rows = KPI + supporting metrics, columns = dimension members with values).
- `scorecard regenerate` — rebuild design + compute.
- `scorecard strategic|operational` — override/confirm type.
- `scorecard analyze <n> [Region=East]` — double-click drill-down: launches `agentic_answer` scoped to that outcome/cell, with cell values injected as context.
- `briefing regenerate` — now consumes scorecard (structure + cells) instead of just schema + KG.

## Briefing rework

New `briefing_prompt.md` outputs `executive_summary` + `slides[]` (one per outcome: key takeaways + dimension highlights), grounded in scorecard cell values. Replaces the old `priority_insights`/`suggested_questions` shape; migrates `briefing.json`.

## Out of scope

Frontend. But the JSON contract (matrix with filter-keyed cells) is designed as the foundation for it.

## Sequencing

Prerequisite: the "Priorities Generation Quality" section below (validator + blueprint + few-shot bank) must land first — the scorecard is only as good as `priorities.json`. Its steps 1–5 run before this list.

1. `scorecard_prompt.md` + `build_scorecard()` in `builder.py` (design only, no compute).
2. `scorecard.json` persistence in `Project` + `scorecard` / `scorecard regenerate` + `scorecard strategic|operational` in shell.
3. `scorecard_compute_prompt.md` + sandbox matrix compute.
4. `scorecard analyze` drill-down (reuse `agentic_answer`, inject scorecard context).
5. Briefing rework (`briefing_prompt.md`, `generate_briefing` signature, `do_briefing`).
6. Update README/critique; verify on both `SalesOrders` and `Pipeline Analytics`.

## Open question (deferred)

**Compute cell granularity** — for multi-dimensional outcomes, should cells include cross-dimension combos (Region × Category) or just per-dimension member values plus overall? Starting point: per-dimension members + overall (simpler, cheaper); cross-tab combos treated as a later enhancement.

---

# Priorities Generation Quality (foundation for the scorecard)

**Phase 0 — prerequisite for all scorecard work above.** Do this before the scorecard sequencing list. The scorecard is only as good as the `priorities.json` it builds on. Current quality problems found by auditing Pipeline Analytics output:

| Problem | Example from the audit |
|---|---|
| ACT stage never emitted (all priorities stop at WHERE) | Every priority ends at a WHERE question |
| Duplicated metrics (same measure × lens repeated) | `Average Deal Size` appears 3× in P3 (supporting + 2 KPIs); `Win Rate by Deal Stage` ≈ `Stage Win Rate Delta` |
| Naming violations (lens/dimension words in names) | `Account Coverage Concentration`, `Time-in-Stage Variance`, `Win Rate by Deal Stage` |
| Computability (references columns not in schema) | `Opportunity Distribution Shift` references "segments"/"geographic" — not in schema |
| Question→KPI alignment drift | "Where are we under-penetrating?" → KPI is concentration, not penetration |
| Not a single scalar value (per-X distribution baked into the formula) | `Win Rate by Deal Stage`, `Agent Contribution Shift`, `Product Mix Shift` — produce one value *per agent/stage/product*, not one number |

## Root cause

We patched the prompt twice (story arcs, ontology, naming rules) but the model still copies the **example's structure** (domain-specific names, 2-question priorities ending at WHERE) instead of following the **rules**. Patching examples per dataset is a losing game: a new dataset (capacity planning, GTM territory design) will break every hard-coded example.

Note: a few-shot bank (below) may look like patching, but it is not the same failure mode — the bank is a *set* of examples retrieved by schema shape and gated by the validator, not a single hard-coded EXAMPLE hard-wired into the main prompt. The two are deliberately different mechanisms.

## Decision

Build the fix as **architecture, not examples** — three cooperating pieces:

1. **O3 — Blueprint pass (two-pass generation).** Pass 1: the LLM produces a dataset-specific *blueprint* — inferred domain, value chain mapped from the schema (upstream/midstream/downstream), computable measure candidates, and question→KPI pre-commitments. Pass 2: authoring is constrained to the blueprint, so it never invents a domain or a non-computable metric. The value chain is *derived from the schema*, not templated, so it generalizes to any dataset.
2. **O2 — Deterministic validator + repair loop.** A Python validator checks output against generic, schema-derived rules (no domain knowledge): `metric` must be a real schema column; **scalar — the `measurement` must resolve to a single aggregate value, not a per-X breakdown (reject "per X", "each X's share", "by X" formulas); a dimension breakdown belongs in the scorecard's columns, never in the metric definition**; name hygiene (reject lens words + dimension column names + "by X"); uniqueness (same metric column + near-identical measurement within a priority); arc (first question WHAT, last ACT); influences in-question only, no self-reference; counts 2–5 / 1–3 / 3–7; delta keywords in measurement. On violations → repair prompt (schema + draft + exact violation list) → regenerate → revalidate (max 2–3 passes), else surface to user. This is the safety net: ~80% of today's failure classes are deterministically checkable, and it's dataset-agnostic by construction.
3. **Few-shot prompt bank (curated, not patched).** A small bank of high-quality examples (Sales pipeline, E-commerce, Capacity Planning, GTM Territory Design, …) retrieved at runtime by schema shape (columns, dtypes, domain keywords) and injected as few-shot context. Anchors a small model with concrete structure *without* hard-coding any single dataset into the main prompt. Bank examples must themselves pass the O2 validator, so bad patterns can't propagate.

## Design notes / guardrails

- The main `priorities_prompt.md` becomes rules-heavy and example-light; concrete structure comes from the retrieved few-shot bank, not from a fixed EXAMPLE block.
- Examples in the bank are marked "illustrative — do not copy structure".
- **Interim state:** until the bank ships (step 3 below), the e-commerce EXAMPLE block stays in `priorities_prompt.md` as the known failure mode — the two-pass + validator steps land first and catch its structural copying before the bank replaces it.
- Keep the CLI unchanged: `priorities regenerate` still emits `priorities.json`; the new pipeline lives behind it.
- **Line-item contract (scorecard-enabling):** every KPI and supporting metric must be a single-line item — a unique stable `name`, one scalar `value` (from `measurement`), a `metric` column, and an optional `format`/`unit`. This guarantees a dashboard renders one row per metric with one number; per-dimension breakdowns are the scorecard's columns, never part of the metric. Duplicated names must not collapse silently (fix `graph.build_from` dedup policy) so each line item stays distinct.

## Sequencing

1. Write O2 validator (`src/analyst/validation.py`) + wire a repair loop into `identify_priorities` in `builder.py` — validate the existing Pipeline Analytics output and confirm it flags today's findings.
2. Add the O3 blueprint pass (new `blueprint_prompt.md` + `build_priority_blueprint()`), keeping authoring single-pass but constrained.
3. Seed the few-shot bank with validated examples; add schema-shape retrieval.
4. Verify on `SalesOrders` and `Pipeline Analytics`; then stress-test with a novel dataset (capacity planning / GTM territory design) to prove generalization.
5. Revisit after the scorecard is stable — blueprint + validator feed naturally into scorecard design/compute.

**Status:** O3 blueprint pass (two-pass generation) implemented 2026-08-12 — `blueprint_prompt.md` + `build_priority_blueprint()` in `builder.py`; candidates are filtered deterministically through the same data gates compute uses (`_precheck_measurement` + column membership) so only provably computable measures reach the authoring prompt, which is constrained to them (`{blueprint}` block in `priorities_prompt.md`). The blocked `not_computable` clutter also landed: `compute_priority_values` now writes failures to a compact `skipped` map on the result envelope instead of persisted value records, surfaced via `priorities skipped <n>`. The definition contract landed 2026-08-13: authored KPIs/operational metrics must carry `form`/`compare`/`unit` (enforced by `validate_priority_metrics()` in `builder.py`, reusing the exact compute gates), a deterministic violation triggers ONE repair pass inside `identify_priorities`, and metrics still failing are excluded (returned as `excluded_metrics`, surfaced in the shell, never persisted as metrics). Few-shot bank (step 3) remains future work.

---

## Compute tier performance — spec + deterministic template (implemented 2026-08-02)

**Observed problem (real run, Pipeline Analytics, `priorities compute 1`, CPU-only model ~2.5 min/call):** the compute tier asks the LLM to generate ONE giant pandas script covering all 24 metrics (~400–700 lines / ~1500–3000 output tokens). Wall time at "Generating compute script" is **3–7+ min in a single call**, and one bad line fails the whole script (real failure: LLM wrote `.sort_value()` instead of `.sort_values()` on a PeriodArray → `AttributeError` → full 24-metric repair pass). Also fixed this session: `resolve_period` returned `definition_text` with a literal `{date_column}` placeholder unsubstituted, forcing the compute script to guess the date column.

**Decision — hybrid spec + deterministic template (implemented):** the LLM stops writing pandas. It emits a compact per-metric **spec**, and a fixed template builds and runs the script. LLM output drops ~10x → generation ~30–90s; execution is deterministic; a bad spec fails one metric, not the whole run.

- **Spec schema (per metric):** `{name, agg, value_column, condition?, numerator/denominator (for ratio/share), compare, unit}`.
- **Agg enum:** `count | sum | mean | median | std | ratio | share | topk_share`.
- **Compare enum:** `level | pct_change | pp_change | rate_ratio` — forces the LLM to resolve the "period-over-period change" ambiguity (pp vs pct) explicitly instead of free-riding on prose.
- **Template builder:** `build_metric_script(specs, period)` — fixed Python consuming the shared period (current/prior masks) + spec list; emits the one `print(json.dumps(...))`; no LLM in the execution path. Each metric is wrapped in its own try/except.
- **Per executive question:** one spec `ask_json` per EQ (not one giant call for all metrics); missing/failed metrics get a spec-level repair pass (cap 2 attempts).
- **Non-scalar pre-filter (added after a real run, then relaxed by the operator DSL):** the repair loop once burned 170s re-asking the LLM for a metric the scalar schema *cannot express*. First cut: `compute_priority_values` deterministically pre-filtered such measurements (`per <dimension>`, `each <dim>`, `by <dim>`, `first-time`, `new agent/account`, `top <n>%`, `percentile`, `distinct/unique`) → immediate `not_computable`. That pre-filter is now **relaxed**: the operator DSL (below) can express all of those, so they flow to the LLM; only residual *data-limited* cases (e.g. true dwell time needs stage-entry timestamps) are hard-filtered, and their `not_computable` records carry `missing_primitive` → "new primitives suggested" summary line.
- **Operator DSL (spec v2, implemented 2026-08-02; design in `metric-spec-v2-composable-operator-dsl.md`):** the spec schema gained composition — `prep` derived columns (`derive.days_between`, `year_of`, `month_of`, `arithmetic` AST-validated/rewritten, computed once per EQ and shared) and `steps` (`group_by → inner_agg → outer_agg` DAX-iterator collapse, `new` first-occurrence counts, `count_distinct` as an agg/denominator, fractional `topk_share` `k` ∈ (0,1] for top-k%), plus a sandboxed `kind: "custom"` escape hatch (`source: "custom"`) and `input_ref` measure-composition (level-only). On Pipeline Analytics this makes ~14 of the 15 previously-inexpressible metrics computable.
- **Per-EQ persistence + resume:** `compute_priority_values(pri, df, schema_str, existing, on_progress)` — the shell persists after each executive question and reuses already-recorded metrics on re-run, so a 15+ min compute survives Ctrl+C. Resume is gated on base-current (engine version + definition + data fingerprints all match) so engine bumps / data reloads force a genuine full recompute.
- **Post-run hardening (2026-08-02):** group-step `outer_agg` defaults to `mean`; the data-limited pre-filter catches stage-progression / stage-to-stage / days-in-stage phrasings; zero-prior `pct_change`/`rate_ratio` nulls carry an explicit `null_reason` ("no prior-period baseline (prior value is 0)") instead of a generic null; `COMPUTE_ENGINE_VERSION` is stamped on every stored result and gates staleness.
- **Verification tier (2026-08-02; design + status in `priority-value-verification-tier.md`):** every record persists its `spec` and the result persists machine-readable period bounds. `compute` auto-runs Layer 0 (deterministic plausibility keyed on spec agg/compare + unit) + Layer 1 (independent parent-process re-derivation of simple v1 specs within 1e-6), setting `verified`/`verification` and printing a one-line summary. `priorities verify <n>` runs L0+L1 again then Layer 2 — one LLM call asking whether each value matches the measurement intent + sampled rows — which is **flag-only** (can only unset `verified`). The Genie-style semantic check is what catches silent basis substitution (stage metrics computed from cycle time; distinct metrics collapsed to one win rate).
- **Closed expressibility surface (2026-08-02, replaces the "drop inexpressible metrics" item below):** the scalar failure modes found on real runs were two genuine DSL gaps plus one wrong engine semantic, all fixed at the engine level so a correct spec ALWAYS exists: (1) FORM-1 `agg` may now target a `prep`-derived column — closes `mean(difference between A and B)` / cycle-time metrics; (2) a `group` step accepts `group_by: null` as a whole-frame scalar; (3) `share` with `value_column: null` is a **count share** (numerator count+condition / denominator count) — closes "share of orders using X" (the old sum-based default would have been wrong semantics, which is why the LLM used to omit it); (4) `median` joined `_AGGS`/`_INNER_AGGS`/`_OUTER_AGGS` + executor + L1 re-derivation. `priority_spec_prompt.md` gained a **measurement→form routing table** + the two previously-missing worked examples; omitted specs are retried once in the repair pass instead of dropped on attempt 1. `tests/test_spec_expressibility.py` locks every expressible shape (validate → execute → L1 match) so a DSL regression fails CI instead of surfacing as an honest-but-wrong `not_computable`. Real check: on SalesOrders, `Express Ship Mode Adoption Rate` and `Order-to-Ship Cycle Time Change` went from not-computable to computed after this.
- **Dimension breakdowns (2026-08-02; the roadmap's "scorecard columns" made concrete):** `priorities compute <n>` now asks the LLM for **ONE schema-validated categorical dimension** per priority (`suggest_breakdown_dimensions`; candidates are text-typed columns with 2–50 distinct values and rows in both current/prior windows; invalid/absent LLM picks fall back to the top data-backed candidate — never a fabricated column), then `compute_priority_breakdowns` deterministically re-runs each computed metric's **stored `spec`** per member and persists a `{member, current, prior, delta, unit, basis, status, verified}` matrix as `breakdowns` + `breakdown_dimensions` per priority. Metrics stay in rows, members become columns. Per-member cells with no rows in a window or a zero prior baseline are honest `not_computable` (row counts are emitted per window so "no rows" ≠ "aggregate 0"). `priorities interpret <n>` reads the matrix ("growth led by the East region, +111% vs +49% overall; West flat") and the viewer renders it. SalesOrders: P1→Region, P2→Customer Segment, P3→Ship Mode, all metrics computed. This is the future `scorecard.json` cell compute, pre-built at the priority level. The "why is segment X weak / which region causes it" drill-down is parked — the stored matrix makes it answerable later. `tests/test_priority_breakdowns.py`.
- **Per-record engine version (2026-08-02):** `COMPUTE_ENGINE_VERSION` is stamped on **each priority record**, not just the file header, and the staleness gate (`_priority_values_are_current`) + resume gate (`base_current`) both check it. Found because the global-only gate let priorities 2/3 silently reuse stale pre-fix records after priority 1 recomputed and bumped the file-level version. `verify` preserves the record's `engine_version`/`breakdowns` when rewriting.
- **Period bounds:** `resolve_period` now also returns machine-readable ISO bounds (`current_start/end`, `prior_start/end`) with a deterministic most-recent-complete-period fallback when the LLM omits them.
- **Fallback:** a metric the template can't express (unknown agg, no column) → `not_computable` with `reason`. Keeps it dataset-agnostic.
- **Values remain seeds:** `verified: false`, `unit`, `basis` — unchanged.
- **Rationale / de-risking:** Pipeline Analytics' 24 measurements are already formulaic (count/sum/mean/std/ratio/share + pct/pp change) by the SCALAR rule, so the enum covers them. This front-loads a slice of the O2 "structured measurement" work — the validator and scorecard inherit it.
- **Progress UX:** `llm.py` gained a heartbeat (elapsed-time tick every 10s on every blocking call; no streaming) so long compute/analyze runs never sit silent.
- **Sequencing:** landed in `feature/priority-compute-tiers` (unit tests pass, incl. pre-filter + resume + per-EQ persistence + operator DSL + hardening + verification tier); verify with `compute 1` / `verify 1` / `analyze 1` / `interpret 1` on Pipeline Analytics; not blocked on O2/O3.
- **Real-data results (2026-08-02, Pipeline Analytics `priorities compute 1`, engine-v3):** period resolved to Q4-2017 vs Q3-2017 on `engage_date`; **11/24 computed, 13 not-computable.** Breakdown of the 13: 1 data-limited (Stage Conversion Rate → "requires stage-entry/transition timestamps"), 3 zero-prior-baseline nulls with `null_reason` confirmed (New Account Acquisition Rate, Pipeline Depth Ratio, Sales Agent Turnover Impact), 2 invalid specs (`value_column 'None'`, `group step value 'None'`), 7 LLM-omitted. Honest read: the majority are **data-grain limits, not DSL or model failures** — `sales_pipeline.csv` is one row per opportunity with a *current* `deal_stage` but no transition history or per-stage timestamps, so stage-progression/dwell-time/velocity metrics are uncomputable by construction. The doc expectation of "~23/24 computed" did not hold on the real model; only data-supported metrics computed.
- **LLM-call latency (2026-08-02):** local model is **Qwen3.6-35B-A3B-UD** on llama.cpp (`localhost:8080/v1`); spec calls ran ~170–210s. Cause: a long hidden **thinking block** (`reasoning_content`) the client discards, plus no `max_tokens`/streaming in `llm.py`. Fix: per-request `thinking_budget_tokens: 512` (llama.cpp honors the body field when no CLI `--reasoning-budget` is set — **no server restart**) + `max_tokens: 8192` backstop, both env-tunable (`LLM_THINKING_BUDGET`, `LLM_MAX_TOKENS`); `chat_with_tools` gets the budget only (answers stay uncapped). Hidden reasoning dropped to ~500 tokens, **but wall time stayed ~120–180s** — remaining bottleneck is answer/content generation, not hidden thinking; a content-length probe is pending. `llm.py` now logs `reasoning content: N chars` per call.
- **Deferred (parked 2026-08-02, post-vacation): drop inexpressible metrics.** The 13 not-computable rows clutter `priorities values`. Plan: (1) `compute_priority_values` stops persisting `not_computable` records → compact `skipped` list (`{name, reason, kind}`) + `priorities skipped <n>`; **single spec attempt per EQ** (kill the 2-attempt repair loop, halving LLM calls); (2) root cause — a `priorities_prompt.md` rule that metrics are only defined when the data grain can express them (no stage-transition/per-stage-timing metrics on flat CSVs), optionally trimming supporting metrics per EQ. Candidates: deterministic duplicate-basis guard (see verification doc) and retiring the L2 LLM check if only computed values survive. **No code written yet.** Note: the DSL-side half of this is now moot — the closed expressibility surface (see above) fixed the engine gaps; what remains is pure UX (not-computable clutter) and data-grain definition rules. The 2-attempt repair loop is now a *feature* (omitted specs are retried once) and should NOT be removed.
