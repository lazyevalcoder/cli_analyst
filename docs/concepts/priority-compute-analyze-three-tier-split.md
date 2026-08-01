# Priority Compute → Analyze (Deep) → Interpret (Three-Tier Split)

A design note for restructuring priority analysis. Currently `priorities analyze <n>` does everything in one long agentic pass (derive base metrics + drill down + narrate). This note proposes splitting it into three tiers so analysis stops re-deriving base metrics, output quality is auditable, and the pipeline becomes scorecard-ready.

**Status:** decided but not started. To be implemented on a separate branch (`feature/priority-compute-tiers`).

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

---

## Proposed data model — `metadata/priority_values.json`

```json
{
  "generated_at": "2026-08-02T12:00:00",
  "priorities": {
    "Pipeline Generation & Stage Progression": {
      "priority_ref": "Pipeline Generation & Stage Progression",
      "fingerprint": "sha256 of sorted (metric name, measurement) pairs",
      "values": {
        "Opportunity Volume Growth": {
          "value": 0.17,
          "period": "current: Q2-2026 vs prior: Q1-2026",
          "measurement": "(Current period Count of opportunity_id − Prior period Count) ÷ Prior period Count, computed quarterly with year-over-year comparison",
          "status": "computed"
        },
        "Product Portfolio Concentration": {
          "value": 0.03,
          "period": "current: Q2-2026 vs prior: Q1-2026",
          "measurement": "Percentage point change in the largest product's opportunity share relative to prior period",
          "status": "computed"
        }
      }
    }
  }
}
```

- `status`: `computed` | `not_computable` | `error` (with a reason string for the last two).
- `fingerprint`: hash of the priority's sorted `(name, measurement)` pairs — cheap staleness check. `priorities regenerate` naturally invalidates it.

### Persistence

- `Project` gains a `priority_values: dict` field, saved/loaded alongside `priorities.json` (see `src/analyst/project.py` `save()`/`load()`).

---

## Compute flow (mirrors the roadmap's scorecard compute)

1. **New prompt `priority_compute_prompt.md`.** Per **executive question** (2–5 per priority → 2–5 LLM calls), the LLM writes **one** pandas script that:
   - Detects the date/period column from the schema and defines current vs prior periods (e.g., most recent full quarter vs prior quarter).
   - Computes every metric in that question to ONE scalar using its `measurement` formula, using EXACT schema column names.
   - Prints `print(json.dumps({"Metric Name": value}))`.
   - A metric that cannot be computed is **omitted** (not fatal).
2. **`builder.compute_priority_values(pri, df, schema_str)`**:
   - For each executive question → `llm.ask` for the script → `sandbox.execute_code(code, df)` (fresh namespace, timeout enforced).
   - Parse the printed JSON, validate keys against metric names.
   - Missing/failed metrics → **one repair pass** (inject errors), cap 2 attempts; survivors marked `not_computable`/`error` with reason.
3. **Persist** to `metadata/priority_values.json`.

---

## Deep upgrade — `priorities analyze <n>`

- Before calling `agentic_answer`:
  - If `priority_values[<n>]` missing, or `fingerprint` ≠ current priority → auto-run `compute` first.
- `format_priority_metric_brief(pri, diagnostic_kg, values=None)` gains a **`PRE-COMPUTED VALUES:`** section appended per metric (heading emitted only when values are supplied).
- `src/analyst/agent.py` (the `metric_brief_str` block, ~line 141): make the Phase-1 instruction conditional:
  - If the brief contains `PRE-COMPUTED VALUES` → "interpret these values; do NOT recompute base metrics (verify once only if a value looks wrong)".
  - Otherwise → keep the existing "compute every KPI" wording.
- Phase 2 (dimension drill-down for OFF KPIs) is unchanged — this is where the agentic loop now spends its budget.
- `priorities show <n>` can optionally surface stored values alongside definitions.

---

## Interpret (quick tier) — `priorities interpret <n>`

- New prompt `interpret_priority_prompt.md` + `builder.interpret_priority(pri, values)`.
- One `llm.ask` (no sandbox, no tool loop) over the stored values: short per-KPI narrative — value, business read, flag OFF KPIs (negative delta / anomaly per the delta principle).
- Saved to `pri["interpretation_summary"]` (distinct from `analysis_summary`, which the deep tier owns).

---

## Shell surface (extend `do_priorities`, `src/analyst/shell.py:487`)

```
priorities compute <n>     # compute + persist values for priority n, print them
priorities analyze <n>     # deep: auto-compute if stale, then seeded agentic loop
priorities interpret <n>   # quick: auto-compute if stale, one-call narration
priorities values <n>      # print stored values (audit aid)
```

`priorities regenerate` clears `priority_values` (or relies on the fingerprint mismatch to auto-invalidate).

---

## Files

| Action | File |
|---|---|
| New | `src/analyst/prompts/priority_compute_prompt.md` |
| New | `src/analyst/prompts/interpret_priority_prompt.md` |
| Modify | `src/analyst/builder.py` — `compute_priority_values()`, `interpret_priority()`, `priority_fingerprint()`, extend `format_priority_metric_brief()` with `values` |
| Modify | `src/analyst/project.py` — `priority_values` field + persist |
| Modify | `src/analyst/shell.py` — `compute` / `interpret` / `values` subcommands; `analyze` auto-compute |
| Modify | `src/analyst/agent.py` — conditional Phase-1 wording |
| Modify | `README.md` — document new commands |
| Generated | `projects/<name>/metadata/priority_values.json` |

---

## Verification

- Pure-Python parts can be unit-tested with a mocked LLM: fingerprint hashing, JSON parse/validate, brief rendering, auto-compute gating.
- Real compute/analyze runs are LLM calls and stay with the user: `priorities compute 1` then `priorities analyze 1` on Pipeline Analytics, then audit the stored values + seeded deep output (every KPI present with a scalar; OFF-KPI drill-down by DKG dimensions; structured per-KPI insight).
- Confirm `priorities regenerate` invalidates stored values.

---

## Known limitations / risks

- **Measurement quality is the ceiling.** `measurement` is free-text business language; compute reliability depends on the LLM translating it correctly. The O2 validator + O3 blueprint (roadmap Phase 0) that would make measurements structured is "decided but not started." Compute inherits today's measurement quality. This engine is still the right foundation.
- **LLM-written compute code can be wrong.** Values should be treated as seeds/estimates, sanity-checkable (Win Rate ∈ [0,1], deltas plausible) — this doubles as a numeric signal for the future O2 validator.
- **Auto-compute on analyze** adds latency before the deep loop (2–5 code-gen calls). Acceptable; it is far cheaper than re-deriving in the loop.
- **Two summary fields** (`analysis_summary` vs `interpretation_summary`) — `priorities show` must render both clearly.

---

## Roadmap alignment

- This is a per-priority slice of the roadmap's scorecard compute step (`scorecard_compute_prompt.md` in `docs/concepts/roadmap.md`).
- The `value`/`status`/`fingerprint` shape is deliberately compatible with the scorecard's cell model (`{filters, value}`) — a scorecard outcome is a priority's metrics plus dimension columns.
- Sequencing note: roadmap Phase 0 (validator/blueprint/few-shot bank) is a prerequisite for the full scorecard, not for this three-tier split. This work can land before Phase 0.

---

## Plan / next steps

1. Create branch `feature/priority-compute-tiers` off `master`.
2. `Project.priority_values` field + persistence (`project.py`).
3. `priority_compute_prompt.md` + `compute_priority_values()` (`builder.py`).
4. `priorities compute <n>` + `priorities values <n>` in shell.
5. Extend `format_priority_metric_brief` with values; conditional Phase-1 in `agent.py`.
6. `interpret_priority_prompt.md` + `interpret_priority()` + `priorities interpret <n>`.
7. Auto-compute gating in `priorities analyze <n>`.
8. Unit-test pure parts; user runs `compute 1` / `analyze 1` / `interpret 1`; audit.
9. Update `README.md`; merge back to `master` when verified.
