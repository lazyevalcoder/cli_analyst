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

**Status: decided but not started — no code changes yet.**
