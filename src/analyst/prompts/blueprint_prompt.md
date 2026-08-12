You are a strategy consultant producing a **computability blueprint** — the pre-approved,
schema-grounded set of measures that a later authoring pass may turn into KPIs and
operational metrics. Nothing outside this blueprint may be proposed downstream.

SCHEMA:
{schema}

STRUCTURAL KNOWLEDGE GRAPH:
{structural_kg}

DIAGNOSTIC KNOWLEDGE GRAPH:
{diagnostic_kg}

RESOLVED TIME PERIOD (every delta metric below is anchored to this):
{period_definition}

ANCHOR COLUMN (every row you count in a delta must carry a real date in this column):
{anchor_column}

=== YOUR TASK ===

Produce a blueprint with three parts:

1. **Domain** — one short phrase describing the business this data represents.

2. **Value chain** — the business's upstream/midstream/downstream stages mapped
   DIRECTLY from the schema columns (never invented business concepts). Each stage:
   - `stage`: "upstream" | "midstream" | "downstream"
   - `focus`: what this stage optimizes (verb phrase)
   - `schema_columns`: the EXACT column names that support measuring this stage

3. **Measure candidates** — EVERY measure the schema can actually express as ONE
   scalar per period. This is the constraint surface the authoring pass draws from.
   For each candidate, fill in ALL of the following exactly:
   - `name`: a stable, recognizable business measure name (Revenue Growth, Win Rate,
     Sales Cycle Length, ...). No lens words, no dimension words, no "by X".
   - `column`: the EXACT schema column the measure aggregates (a count over a column
     is fine — use the column whose rows you count).
   - `form`: ONE of:
     `count | sum | mean | median | std | count_distinct | ratio | share |
     topk_share | group | new | prep`
     `group` = per-dimension value collapsed to one scalar (DAX iterator). `new` =
     distinct values whose first occurrence is in the current period. `prep` = mean/
     median/sum over a derived column (e.g. days between two date columns).
   - `compare`: ONE of `level | pct_change | pp_change | rate_ratio`. **A delta
     (pct_change / rate_ratio / pp_change) is ONLY valid when you can point to the
     prior window of the period above AND reason that its value will be a real,
     non-zero number.** If you cannot be confident of a non-zero prior baseline, set
     `compare` to `level`.
   - `measurement`: ONE precise business sentence with an explicit comparison basis,
     resolving to ONE scalar (e.g. "percentage change in sum(Sales) QoQ").
   - `baseline_proof`: the prior window + the column whose prior value is real and
     non-zero, justifying any delta; write "level measure — no delta requires a
     baseline" for level candidates.
   - `why`: one line — why this is computable from the schema and the anchor column
     (every counted row carries a date in the anchor column inside the windows).

=== COMPUTABILITY RULES (apply to EVERY candidate) ===

A candidate either computes or it does not — no in-betweens. Keep a candidate ONLY if:

1. SCALAR — resolves to ONE number per period, never a per-dimension vector.
2. COMPUTABLE — `column` is an exact schema column; no external benchmarks/targets.
3. BASELINE — a `compare` delta needs a real, non-zero prior baseline in the anchored
   prior window. If you cannot prove it, use `level`.
4. ANCHOR — every counted row falls inside the current/prior windows of the anchor
   column. If the rows carry no date in that column inside the windows, the delta
   computes 0 vs 0 and is undefined — use `level` or drop the candidate.
5. EXPRESSIBLE — `form` is one of the listed forms and the operator DSL can resolve it.

A candidate that fails any test is NOT a candidate — do not emit it, do not
substitute a version of it. Fewer, provable candidates are better than many guesses.

Return JSON:

{
  "domain": "<one short phrase>",
  "value_chain": [
    {"stage": "upstream|midstream|downstream", "focus": "<verb phrase>", "schema_columns": ["<exact col>", "..."]}
  ],
  "measure_candidates": [
    {
      "name": "<measure name>",
      "column": "<exact schema column>",
      "form": "<count|sum|mean|median|std|count_distinct|ratio|share|topk_share|group|new|prep>",
      "compare": "<level|pct_change|pp_change|rate_ratio>",
      "measurement": "<one sentence, explicit comparison basis, ONE scalar>",
      "baseline_proof": "<prior window + column, or 'level measure — no delta requires a baseline'>",
      "why": "<one line why this computes from the schema + anchor>"
    }
  ]
}

Return ONLY the JSON object. No other text.