# Verify Tier — Plan

A design note for a verification pass over computed priority-metric values. The analog: Databricks Genie's **verifier** agent (validates results, triggers re-runs or clarifying questions) and its **benchmarks** (test questions → expected answers, scored). Our `verified` flag already exists in every value record but is hardcoded `False` — this note makes it mean something.

**Status:** implemented 2026-08-02 (`feature/priority-compute-tiers`). Layers 0–2 land on top of the hardened compute tier; `priorities verify <n>` runs the full stack and persists per-metric verdicts. 101 tests pass (incl. `TestLLMClientParams`).

---

## Goal

Make `verified` truthful: after compute, every metric value carries a per-metric verification result.

- Deterministic checks run for free (no LLM).
- An optional LLM verifier checks the one thing the deterministic template can never catch: that the **spec faithfully encodes the measurement**. The template guarantees the math is right *given the spec*; only the LLM can judge whether the spec is the right spec.

## Why now / what blocks it

Two gaps found in the current code:

1. `verified: False` is set in every value record in `compute_priority_values` and never flipped anywhere.
2. The **spec used for each metric is not persisted** — records only store `{name, unit, basis, value, measurement}`. A verifier needs the spec to re-check.

## Prerequisite — persist the spec

Add `spec` (the validated spec dict) to each value record in `compute_priority_values` (the record-building blocks in `src/analyst/builder.py`). Needed for the LLM verifier and for auditability.

- Does NOT affect `priority_fingerprint` or resume: `_priority_values_are_current` keys on metric names + fingerprints, not record contents.

---

## Layer 0 — deterministic plausibility checks (no LLM)

A `_check_value(rec)` rule set keyed on `unit` + `compare`:

| rule | applies to |
|---|---|
| value ≥ 0 | `count`, `count_distinct`, currency sums |
| 0 ≤ value ≤ 1 | `share`, `topk_share` (unit `ratio`/`percent`) |
| finite, non-zero denominator | `pct_change`, `rate_ratio` (already null-guarded) |
| finite | `pp_change`, everything |
| not NaN | everything (already handled) |

Output per metric: `{ok, note}`. Any failure → `verified: False` + note.

Runs automatically at the end of `compute_priority_values` (cheap; via the `on_progress` merge or a post-loop pass).

## Layer 1 — independent re-derivation cross-check (deterministic)

For simple v1 specs (`count|sum|mean|std|count_distinct`, and `ratio`/`share` with count/sum sub-specs), recompute the current value **in the parent process** with direct pandas — independent of the sandbox template — and compare to the recorded value within 1e-6 relative.

- Catches template/emission regressions on the **real** df (the pytest suite only covers synthetic fixtures).
- Composed v2 specs (group/new/custom): skip in v1; their determinism is already unit-tested.

## Layer 2 — LLM semantic verifier (the Genie verifier)

New prompt `verify_priority_prompt.md` + `verify_priority_values(pri, df, values)` in `builder.py`. One compact call per priority: schema, period definition, and per metric `{name, measurement, spec, value, unit, compare}` + a 3–5-row sample of the columns each spec touches. Asks per metric: *"does the computed value match the measurement's intent and the data?"* → JSON `{metric: {ok, note}}`.

**Outcome model (recommended):**

- Layer 0 + 1 pass **and** LLM ok → `verified: True`, `verification: {checks: [...], llm_note, at}`
- Any layer fails → `verified: False`, `verification: {checks, llm_note, at}`
- Failure is **flag-only in v1** — surfaced in `priorities show`/`values`, NO auto-repair (blind re-asks already burned 170s before; keep failures human-visible).

---

## Shell integration

- `priorities verify <n>` — runs Layer 0+1 always, Layer 2 (LLM call, heartbeat + label like other calls) on request; updates stored records + `project.save()`.
- `compute` auto-runs Layer 0+1 and prints a one-line verification summary.
- `format_priority_metric_brief` already prints `VERIFIED`/`UNVERIFIED` — becomes truthful.

## Files

- `src/analyst/builder.py`: `verify_priority_values`, `_check_value`, `_recompute_value`; persist `spec` in compute loop; set `verified`/`verification` on records.
- `src/analyst/shell.py`: `do_priorities` gains `verify <n>`; auto Layer 0/1 in `_ensure_priority_values`.
- `src/analyst/prompts/verify_priority_prompt.md` (new — `prompts.load` picks it up automatically).
- `tests/test_priority_tiers.py`: Layer 0 rule tests, Layer 1 recompute match, spec-persisted test, verify integration (mocked Layer 2), `verified=True/False` propagation.
- Docs: three-tier doc gains a "verification" step; roadmap section.

## Sequencing

1. Persist `spec` on records (+ test).
2. Layer 0 checks + auto-run + summary (+ tests).
3. Layer 1 recompute for simple specs (+ tests).
4. `priorities verify <n>` + prompt + Layer 2 (mocked test).
5. Docs.

---

## Open decisions (resolved 2026-08-02)

1. **`verified: True` semantics** — L0+L1 alone set it; the LLM (L2) is advisory and can only unset/annotate. Implemented in `_verify_layers` (`verified = l0_ok and l1_ok`) and `verify_priority_values` (only flips `verified` to `False`).
2. **Layer 2 trigger** — explicit `priorities verify <n>` only; `compute` auto-runs L0+L1 and prints a one-line summary. Implemented.
3. **On LLM disagreement** — flag-only (no auto-repair). Implemented; failures surface in `priorities values <n>` and the verify summary line.
4. **Layer 1 scope** — minimal recompute for simple v1 specs only; composed v2 specs are skipped with an explicit note. Implemented. A dev-facing benchmark harness beyond the pytest suite remains future work.

## Real-data outcome (2026-08-02, engine-v3)

Ran automatically at the end of `priorities compute 1` on Pipeline Analytics (11 computed / 13 not-computable):

- **L0:** pass 11 / fail 0.
- **L1:** match 0 / mismatch 5 / skipped 6 — the mismatches are real signal, but most computed metrics are composed v2 specs (skipped) or simple specs that disagreed on re-derivation (mismatch), so `verified: True` landed on only the 6 pass-through records.
- **Collision class L1 cannot catch:** L1 re-derives from the *same spec*, so two distinct metrics computed from the same (wrong) spec both pass: `Time-in-Stage Velocity` == `Stage Stall Duration` (−0.0329, cycle-days basis) and `Engagement Frequency Momentum` == `Account Engagement Intensity` (+0.0074, per-account count basis). A deterministic **duplicate-basis guard** (identical `basis`+`value` across distinct metric names → flag/drop) is the cheap fix; L2 is the expensive one.
- **L2 not yet run:** `priorities verify 1` pending. L2 remains the only layer that can catch basis substitution — keep it on the short list.

## Related docs

- `metric-spec-v2-composable-operator-dsl.md` — the operator DSL this verifies.
- `priority-compute-analyze-three-tier-split.md` — compute → analyze (deep) → interpret (quick); verification is a natural sub-step of compute.
- `roadmap.md` — "Compute tier performance" (spec + template) and O2/O3 priorities-quality work.
