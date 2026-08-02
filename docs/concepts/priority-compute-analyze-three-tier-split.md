# Priority Compute → Analyze (Deep) → Interpret (Three-Tier Split)

A design note for restructuring priority analysis. Currently `priorities analyze <n>` does everything in one long agentic pass (derive base metrics + drill down + narrate). This note proposes splitting it into three tiers so analysis stops re-deriving base metrics, output quality is auditable, and the pipeline becomes scorecard-ready.

**Status:** implemented on branch `feature/priority-compute-tiers`. The compute tier shipped with the **spec + deterministic template** approach (see `roadmap.md` "Compute tier performance"): per executive question the LLM emits a compact per-metric **spec** (`{name, agg, value_column, condition?, numerator/denominator, compare, unit}`), and `build_metric_script(specs, period)` builds the pandas script deterministically — the LLM no longer writes pandas. **Operator DSL (spec v2, 2026-08-02; see `metric-spec-v2-composable-operator-dsl.md`):** the schema gained `prep` derived columns and `steps` (group→outer collapse, `new` first-occurrence, `count_distinct`, fractional `topk_share`), a sandboxed `kind: "custom"` escape hatch, and `input_ref` measure-composition — making ~14 of the 15 previously-inexpressible metrics on Pipeline Analytics computable. **Pre-filter (2026-08-02):** the original SCALAR-rule hard-filter (per-group/first-time/top-%/distinct measurements → immediate `not_computable`) is **relaxed** — those now flow to the LLM; only residual *data-limited* cases (e.g. true dwell time needs stage-entry timestamps) are hard-filtered, and their records carry `missing_primitive` → "new primitives suggested" summary line. Repair re-asks for *invalid* specs; since 2026-08-02 a spec that is *omitted* on attempt 1 is also retried once in the repair pass before being marked `not_computable` (a transient LLM omission self-heals; the result is still computed-or-not-computable, never a substituted value). **Dimension breakdowns (2026-08-02):** `priorities compute <n>` also asks the LLM for ONE schema-validated categorical dimension per priority (`suggest_breakdown_dimensions`, candidate columns are text-typed with 2–50 distinct values and rows in both windows), then `compute_priority_breakdowns` deterministically re-runs each computed metric's stored `spec` per member (metrics in rows × members in columns, `{current, prior, delta}`), persisting `breakdown_dimensions` + `breakdowns` per priority. `interpret` reads the matrix; per-member cells with no data / zero baseline are honest `not_computable`. `COMPUTE_ENGINE_VERSION` is now stamped **per priority record** so a stale record can never be silently reused when the engine changes. **Per-EQ persistence:** `compute_priority_values` accepts `existing`/`on_progress` so the shell persists after each executive question and resumes partial runs (Ctrl+C keeps completed EQs). **Post-run hardening (2026-08-02):** group-step `outer_agg` defaults to `mean`; the data-limited pre-filter catches stage-progression phrasings; zero-prior `pct_change`/`rate_ratio` nulls carry an explicit `null_reason`; a `COMPUTE_ENGINE_VERSION` staleness gate forces full recompute on engine changes (resume is gated on base-current). **Verification step (2026-08-02; see `priority-value-verification-tier.md`):** every record persists its `spec` and the result persists machine-readable period bounds; compute auto-runs Layer 0 (deterministic plausibility) + Layer 1 (independent parent-process re-derivation within 1e-6), setting `verified`/`verification`; `priorities verify <n>` adds Layer 2 (LLM semantic check) which can only unset `verified`. Unit tests landed; awaiting real-model verification — `compute 1` / `verify 1` / `analyze 1` / `interpret 1` on Pipeline Analytics.

---

## Real-data validation (2026-08-02)

A real `priorities compute 1` on Pipeline Analytics landed **11/24 computed, 13 not-computable** — the "~14 of 15 previously-inexpressible metrics now computable" claim holds only where the *data grain* supports the measurement; the residual not-computable metrics are data-limited (stage-transition / per-stage-timing measurements need timestamps the CSV lacks), not DSL gaps. Latency investigation: the local model is Qwen3.6-35B-A3B-UD on llama.cpp; spec calls ~170–210s were dominated by a discarded hidden thinking block → per-request `thinking_budget_tokens` (512) + a `max_tokens` backstop were added to `llm.py` (no server restart). **Parked (post-vacation):** drop inexpressible metrics to a `skipped` list and constrain priority generation to the data grain — see `roadmap.md` "Compute tier performance".

---

## What (the proposal in one paragraph)

Break `priorities analyze <n>` into three independent commands:

1. **`priorities compute <n>`** — resolve every KPI + supporting metric in priority `n` to **one scalar value** each (like a pivot-table calculated field dragged into the Values area → a single number), and persist them to `metadata/priority_values.json`.
2. **`priorities analyze <n>`** (existing command, upgraded to *deep*) — auto-compute if values are missing/stale, then seed the agentic loop with the stored values so the loop's budget goes to dimension/lens drill-down, not re-deriving base metrics.
3. **`priorities interpret <n>`** — cheap, single-LLM-call narration of stored values ("quick" tier). No 15-step loop.

The result is a cost ladder: compute (a few code-gen LLM calls) → interpret (one short call) → analyze-deep (the full agentic loop, but seeded).

---

## Why

- The current single-pass `priorities analyze` spends 3–6 of its first steps re-deriving the same base metrics on every run.
- Compute failures currently poison the whole run (see the truncated 9-step fallback stored in `analysis_summary` for Pipeline Analytics P1).
- There is no persistent numeric artifact. Nothing answers "what is Product Portfolio Concentration right now?" without re-running analysis.
- The roadmap's scorecard needs exactly this: a filter-keyed matrix of computed cell values. Per-priority compute is that engine, built early and per-priority. Not throwaway work.

---

## Current state (before this change)

- `priorities regenerate` → `priorities.json`, where each priority has `executive_questions[]` → `kpis[]` + `supporting_metrics[]`, each with `name`, `metric` (source column), `description`, `measurement` (free-text formula).
- `priorities analyze <n>` → `agentic_answer()`:
  - Phase 1: `reason_and_plan()` builds a reasoning + plan.
  - Phase 2: prints plan.
  - Phase 3: 15-step (default) tool-calling loop with a shared pandas `df` namespace (`execute_code`, `final_answer`, `lookup_metric`, `traverse_graph`).
  - Phase 4: forced final synthesis; falls back to a concatenation of successful step outputs.
- `format_priority_metric_brief(pri, diagnostic_kg)` renders KPIs + supporting metrics + DKG drill-down dimensions into a prompt brief, injected into the system prompt as the METRIC BRIEF with a TWO-PHASE EXECUTION instruction (Phase 1: compute every KPI; Phase 2: drill down only OFF KPIs).
- No computed values are persisted anywhere. `metric_catalog.json` stores *definitions*, not *values*.
- Checkpoint system: after `max_iterations` (15, env `MAX_ITERATIONS`), prompt `Continue for {continuation_block} (5) more steps? (y/N)`; decline → Phase 4.

### Pain points observed

- `analysis_summary` from the pre-fix run of Pipeline Analytics P1 is a raw truncated step dump ("Analysis completed with 9 successful steps"), unusable for auditing.
- Phase-4 forced synthesis previously dropped `execute_code` results (fixed already, but the symptom shows the fragility of one monolithic pass).
- Repeated analyses re-pay the base-metric computation cost every time.

---

## Design decisions (confirmed with user)

- **Compute scope:** one scalar per metric, full stop. No dimension matrices, no per-X vectors. The pivot-field analogy is authoritative: drag the calculated field into Rows → a single value.
- **Staleness:** auto-run `compute` if values are missing or stale. Manual `priorities compute <n>` still exists for explicit rebuilds.
- **Existing command:** `priorities analyze <n>` is upgraded to *deep* (seeded by computed values), keeping one analysis entry point. No parallel `analyze-deep` command.
- **Delta principle:** leaders think in deltas. Each KPI's `measurement` embeds its comparison basis (growth rates, pp changes, ratios), so the single scalar already encodes current-vs-prior. No separate delta value is stored.
- **SCALAR rule:** every metric resolves to ONE aggregate scalar, never a per-X breakdown. Dimension drill-down belongs to the deep tier and the future scorecard's columns, not in the metric definition.

### Validation-driven decisions (from a first-principles + critique review)

These sharpen the model against correctness gaps found in review:

- **Definition + data staleness (two independent triggers):** staleness = definition fingerprint mismatch **OR** data fingerprint mismatch. A fresh data load must invalidate values even when `measurement` text is unchanged. A data fingerprint (hash of data shape + row count + latest date value) is computed at compute time and stored.
- **Canonical period:** the date/period resolution is done **once per compute run** via a single schema-introspection step and stored as `period_definition`; the single compute script consumes it. No per-question period guessing.
- **Unit on every scalar:** values carry `unit` (`pp` | `ratio` | `count` | `currency` | `%` …); percentages are stored as fractions (0.17 = 17%) so `0.03` vs `3pp` is unambiguous.
- **Basis retained:** `basis` records the current/prior raw figures when cheaply derivable, so deltas stay recomputable and verifiable (delta-only storage is rejected).
- **`verified` flag:** values start `verified: false`. A human or the future O2 validator flips it on acceptance. Unverified seeds are narrated/used with that caveat — persistence makes values falsifiable, and the flag makes that explicit.
- **One OFF definition:** "OFF KPI" is defined once (delta < threshold OR outside [min,max] band) and consumed by both deep and interpret tiers — no per-tier drift that lets summaries contradict each other.
- **Metric-level repair:** compute repair targets individual metric keys, not whole executive questions, so one bad script line can't drop 5 KPIs at once.
- **`regenerate` always clears `priority_values`** (explicit invalidation); the fingerprints remain a safety net.
- **Value model is `(metric, filters)` — additive to the scorecard:** today `filters: []` (scalar per metric, per the SCALAR rule); the scorecard later extends by adding filter keys. No remodel needed.

---

## Proposed data model — `metadata/priority_values.json`

```json
{
  "generated_at": "2026-08-02T12:00:00",
  "data_fingerprint": "sha256 of data shape + row count + latest date value (invalidate on data reload)",
  "period_definition": "current: Q2-2026 (most recent full quarter) vs prior: Q1-2026 — resolved once per run",
  "priorities": {
    "Pipeline Generation & Stage Progression": {
      "priority_ref": "Pipeline Generation & Stage Progression",
      "fingerprint": "sha256 of sorted (metric name, measurement) pairs",
      "values": {
        "Opportunity Volume Growth": {
          "filters": [],
          "value": 0.17,
          "unit": "ratio",
          "period": "current: Q2-2026 vs prior: Q1-2026",
          "basis": "current 412 vs prior 352",
          "measurement": "(Current period Count of opportunity_id − Prior period Count) ÷ Prior period Count, computed quarterly with year-over-year comparison",
          "verified": false,
          "status": "computed"
        },
        "Product Portfolio Concentration": {
          "filters": [],
          "value": 0.03,
          "unit": "pp",
          "period": "current: Q2-2026 vs prior: Q1-2026",
          "basis": "largest product share 34.1% vs 34.0% (prior)",
          "measurement": "Percentage point change in the largest product's opportunity share relative to prior period",
          "verified": false,
          "status": "computed"
        }
      }
    }
  }
}
```

- `status`: `computed` | `not_computable` | `error` (with a reason string for the last two).
- `filters`: `[]` today (one scalar per metric, per the SCALAR rule). The scorecard extends additively by adding filter keys — this is the `(metric, filters)` record shape, not a per-X vector.
- `unit`: `pp` | `ratio` | `count` | `currency` | `%` … Percentages are stored as fractions (`0.17` = 17%), removing scale ambiguity.
- `basis`: current/prior raw figures when cheaply derivable — keeps the delta recomputable and auditable.
- `verified`: `false` until a human or the O2 validator accepts the value; unverified seeds are flagged as such when consumed.
- `fingerprint` (definition): hash of the priority's sorted `(name, measurement)` pairs — catches measurement edits.
- `data_fingerprint` (top-level): hash of data shape/row count/latest date — catches data reloads. **Auto-compute triggers on missing values, definition-fingerprint mismatch, OR data-fingerprint mismatch.**

### Persistence

- `Project` gains a `priority_values: dict` field, saved/loaded alongside `priorities.json` (see `src/analyst/project.py` `save()`/`load()`), including `data_fingerprint` and `period_definition`.
- `priorities regenerate` clears `priority_values` outright (explicit invalidation).

---

## Compute flow (mirrors the roadmap's scorecard compute)

**Update (2026-08-02, from a real run):** the original merged-script design below was replaced by the **spec + deterministic template** approach (details in `roadmap.md`). The LLM stopped writing pandas entirely; it now emits a compact per-metric spec and a fixed template builds the script. The flow:

1. **Schema/period introspection (once per run).** `compute_priority_values` inspects the schema, locates the date/period column, and resolves the canonical current-vs-prior period (e.g., most recent full quarter vs prior quarter). Stored as `period_definition` **plus machine-readable ISO bounds** (`current_start/current_end/prior_start/prior_end`, with a deterministic most-recent-complete-period fallback when the LLM omits them) and injected into the spec prompt — no per-question period guessing.
2. **New prompt `priority_spec_prompt.md`.** ONE compact spec call **per executive question** (~6–8 metrics each, not one giant script for all 24). The LLM emits a JSON array of specs (no code): Form 1 `{name, agg, value_column, condition?, numerator/denominator, compare, unit}` with `agg ∈ count|sum|mean|std|count_distinct|ratio|share|topk_share` and `compare ∈ level|pct_change|pp_change|rate_ratio`, or Form 2 the operator DSL `{prep, steps, compare, unit}` (group→outer collapse, `new`, fractional `topk_share`). LLM output drops ~10x vs writing pandas (30–90s instead of 3–7+ min).
3. **`builder.build_metric_script(specs, period)`.** A fixed Python template consumes the shared period masks + spec list and emits the single `print(json.dumps({...}))`. Deterministic; **each metric is wrapped in its own try/except** so one bad spec fails one metric, never the whole run. No LLM in the execution path.
4. **`builder.compute_priority_values(pri, df, schema_str, existing=None, on_progress=None)`:** pre-filter (only residual *data-limited* measurements, with `missing_primitive`) → per-EQ spec `ask_json` → `_parse_specs` → `_validate_spec` (agg/compare enum + operator-DSL `prep`/`steps`/`custom`/`input_ref` validation + schema-column checks + condition compile/blocklist) → `build_metric_script` → `sandbox.execute_code(code, df)` → parse the printed JSON → **spec-level repair** (re-ask only for *invalid* specs, cap 2 attempts); omissions and inexpressible metrics are marked `not_computable` with reason. `existing` resumes a partial run; `on_progress` persists after each EQ.
5. **Persist** to `metadata/priority_values.json` with `generated_at`, `data_fingerprint`, `period_definition`.

### Original (superseded) design — retained for reference

1. Schema/period introspection once per run.
2. `priority_compute_prompt.md`: ONE script per priority (all metrics across all executive questions in a single LLM call → one `llm.ask`), the LLM writes **one** pandas script.
3. `builder.compute_priority_values`: introspection → ONE `llm.ask` for the merged script → `_strip_blocked_imports` → `sandbox.execute_code`; parse printed JSON; metric-level repair (cap 2 attempts).
4. Persist.

This failed in production: the single giant script took 3–7+ min to generate and one bad line (e.g. `.sort_value()`) failed all 24 metrics at once. Superseded by the spec + template flow above.

---

## Deep upgrade — `priorities analyze <n>`

- Before calling `agentic_answer`:
  - If `priority_values[<n>]` missing, definition `fingerprint` ≠ current priority, or `data_fingerprint` ≠ current data → auto-run `compute` first.
- `format_priority_metric_brief(pri, diagnostic_kg, values=None)` gains a **`PRE-COMPUTED VALUES:`** section appended per metric (heading emitted only when values are supplied).
- `src/analyst/agent.py` (the `metric_brief_str` block, ~line 141): make the Phase-1 instruction conditional:
  - If the brief contains `PRE-COMPUTED VALUES` → "interpret these values; do NOT recompute base metrics (verify once only if a value looks wrong)". Unverified seeds (`verified: false`) are flagged as such.
  - Otherwise → keep the existing "compute every KPI" wording.
- **Missing-value policy:** metrics with `status: not_computable`/`error` have no seed — the loop IS allowed to recompute those once, and the output marks them "recomputed in-loop".
- Phase 2 (dimension drill-down for OFF KPIs) is unchanged — this is where the agentic loop now spends its budget. "OFF" uses the single shared definition (delta < threshold OR outside band) from the brief.
- `priorities show <n>` surfaces stored values (value, unit, period, `verified`, `status`) alongside definitions.

---

## Interpret (quick tier) — `priorities interpret <n>`

- New prompt `interpret_priority_prompt.md` + `builder.interpret_priority(pri, values)`.
- One `llm.ask` (no sandbox, no tool loop) over the stored values: short per-KPI narrative — value + unit, business read, flag OFF KPIs using the **same shared OFF definition** consumed by the deep tier (delta < threshold OR outside band) — no per-tier drift.
- Unverified values are narrated with the "unverified" caveat; `not_computable`/`error` metrics are noted as uncomputable rather than silently skipped.
- Saved to `pri["interpretation_summary"]` with an `interpreted_at` timestamp (distinct from `analysis_summary`, which the deep tier owns; `priorities show` labels both by tier + timestamp).

---

## Shell surface (extend `do_priorities`, `src/analyst/shell.py:487`)

```
priorities compute <n>     # compute + persist values for priority n, print them
priorities analyze <n>     # deep: auto-compute if stale, then seeded agentic loop
priorities interpret <n>   # quick: auto-compute if stale, one-call narration
priorities values <n>      # print stored values (audit aid)
```

`priorities regenerate` clears `priority_values` outright (explicit invalidation; the fingerprints remain a safety net).

---

## Files

| Action | File |
|---|---|
| New | `src/analyst/prompts/priority_spec_prompt.md` (replaces `priority_compute_prompt.md`, which is deleted) |
| New | `src/analyst/prompts/interpret_priority_prompt.md` |
| Modify | `src/analyst/builder.py` — `compute_priority_values()` (per-EQ spec + spec-level repair), `build_metric_script()`, `_parse_specs()`/`_validate_spec()`, `priority_fingerprint()`, `data_fingerprint()`, `resolve_period()` (machine-readable bounds + deterministic fallback), extend `format_priority_metric_brief()` with `values` |
| Modify | `src/analyst/project.py` — `priority_values` field + persist (`data_fingerprint`, `period_definition`) |
| Modify | `src/analyst/shell.py` — `compute` / `interpret` / `values` subcommands; `analyze` auto-compute |
| Modify | `src/analyst/agent.py` — conditional Phase-1 wording |
| Modify | `src/analyst/llm.py` — heartbeat progress on all blocking LLM calls (no streaming) |
| Modify | `README.md` — document new commands + heartbeat |
| Generated | `projects/<name>/metadata/priority_values.json` |

---

## Verification

- Pure-Python parts can be unit-tested with a mocked LLM: definition + data fingerprint hashing, JSON parse/validate, brief rendering, auto-compute gating (missing / def-mismatch / data-mismatch).
- Real compute/analyze runs are LLM calls and stay with the user: `priorities compute 1` then `priorities analyze 1` on Pipeline Analytics, then audit the stored values + seeded deep output (every KPI present with a scalar + unit; OFF-KPI drill-down by DKG dimensions; structured per-KPI insight).
- Confirm `priorities regenerate` clears stored values, and that a **data reload** (changed `data_fingerprint`) triggers auto-recompute on the next `analyze`/`interpret`.

---

## Known limitations / risks

- **Measurement quality is the ceiling.** `measurement` is free-text business language; compute reliability depends on the LLM translating it correctly. The O2 validator + O3 blueprint (roadmap Phase 0) that would make measurements structured is "decided but not started." Compute inherits today's measurement quality. This engine is still the right foundation.
- **LLM-written compute code can be wrong.** Values are treated as seeds/estimates, not authoritative: the `verified` flag, `unit`, and `basis` make them falsifiable, and per-metric try/except + metric-level repair limit blast radius. Sanity-checks (Win Rate ∈ [0,1], deltas plausible) double as a numeric signal for the future O2 validator.
- **Auto-compute on analyze** adds latency before the deep loop (1–3 code-gen calls + one introspection call). Acceptable; it is far cheaper than re-deriving in the loop. Note the `data_fingerprint` can trigger a recompute on every data reload — by design, but be aware analyses after a reload re-pay this cost.
- **Two summary fields** (`analysis_summary` vs `interpretation_summary`) — `priorities show` renders both with tier labels + timestamps; the single shared OFF definition keeps them from contradicting each other.
- **Primary value is persistence/reuse/auditability, not raw cost.** Compute is now a single merged script generation (1 call + up to 1 metric-level repair), far cheaper than the loop's 3–6 re-derive steps; the win is that base values become stable, inspectable, and reusable across `analyze`/`interpret`/`values`/the future scorecard.

---

## Roadmap alignment

- This is a per-priority slice of the roadmap's scorecard compute step (`scorecard_compute_prompt.md` in `docs/concepts/roadmap.md`).
- The value model is a `(metric, filters)` record with `filters: []` today — deliberately compatible with the scorecard's cell model (`{filters, value}`); a scorecard outcome is a priority's metrics with filter keys added additively, no remodel.
- Sequencing note: roadmap Phase 0 (validator/blueprint/few-shot bank) is a prerequisite for the full scorecard, not for this three-tier split. This work can land before Phase 0.

---

## Plan / next steps

1. Create branch `feature/priority-compute-tiers` off `master`.
2. `Project.priority_values` field + persistence incl. `data_fingerprint`/`period_definition` (`project.py`).
3. `priority_spec_prompt.md` + `compute_priority_values()` (per-EQ specs + `build_metric_script` deterministic template + spec validation/repair) (`builder.py`).
4. `priorities compute <n>` + `priorities values <n>` in shell.
5. Extend `format_priority_metric_brief` with values; conditional Phase-1 + missing-value policy in `agent.py`.
6. `interpret_priority_prompt.md` + `interpret_priority()` + `priorities interpret <n>` (shared OFF definition).
7. Auto-compute gating in `priorities analyze <n>` (missing / def-mismatch / data-mismatch).
8. Heartbeat progress on blocking LLM calls (`llm.py`) so long compute/analyze runs never sit silent.
9. Unit-test pure parts (done: 35 tests pass); user runs `compute 1` / `analyze 1` / `interpret 1`; audit.
10. Update `README.md`; merge back to `master` when verified.
