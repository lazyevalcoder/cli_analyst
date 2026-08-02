You are a data analyst. For each metric you are given, produce a compact **compute spec** — NOT pandas code. A deterministic template will turn the specs into an executable script.

SCHEMA:
{schema}

PERIOD DEFINITION (shared, do NOT redefine — consume it):
{period_definition}

METRICS TO SPEC (JSON array; each has name, metric/source column, measurement):
{metrics}

=== YOUR TASK ===
Return a JSON **array** with exactly one object per metric, using EXACTLY the metric's `name`. Two forms are allowed.

FORM 1 — single aggregate (simple metrics):
[
  {{
    "name": "<exact metric name>",
    "agg": "<count|sum|mean|std|count_distinct|ratio|share|topk_share>",
    "value_column": "<exact schema column to aggregate; null for count>",
    "condition": "<optional boolean pandas expression over the period-filtered df, e.g. \"df['won'] == 1\"; null if none>",
    "numerator": {{"agg": "<count|sum|mean|count_distinct>", "value_column": "<column>", "condition": "<optional expression>"}},
    "denominator": {{"agg": "<count|sum|mean|count_distinct>", "value_column": "<column>", "condition": "<optional expression>"}},
    "group_by": "<dimension column for topk_share; null otherwise>",
    "k": <integer >=1 for topk_share top-k members, OR a fraction 0<k<=1 for top-k%; null otherwise>,
    "compare": "<level|pct_change|pp_change|rate_ratio>",
    "unit": "<pp|ratio|count|currency|percent|other>"
  }}
]

FORM 2 — composed operator DSL (per-group / derived / first-time / concentration):
[
  {{
    "name": "<exact metric name>",
    "prep": [
      {{"op": "derive.days_between", "start": "<col>", "end": "<col>", "as": "<new col>"}},
      {{"op": "derive.year_of", "column": "<col>", "as": "<new col>"}},
      {{"op": "derive.month_of", "column": "<col>", "as": "<new col>"}},
      {{"op": "derive.arithmetic", "expr": "<arithmetic over column names only>", "as": "<new col>"}}
    ],
    "steps": [
      {{"op": "group", "group_by": "<dimension>", "inner_agg": "<count|sum|mean|std|min|max|share>",
        "value": "<column or derived name; null if inner_agg=count>", "outer_agg": "<mean|std|max|min|sum>"}},
      {{"op": "new", "value_column": "<column>"}}
    ],
    "compare": "<level|pct_change|pp_change|rate_ratio>",
    "unit": "<pp|ratio|count|currency|percent|other>"
  }}
]

OPERATOR MEANINGS:
- `prep`: derived columns computed once per executive question and shared by all metrics in it. `derive.arithmetic` expr may reference real columns AND earlier derived names, using only + - * / % etc.
- `steps`:
  - `group`: compute `inner_agg` of `value` within each `group_by` group, then collapse with `outer_agg` to ONE scalar (DAX iterator pattern).
    - AVERAGEX(VALUES(agent), COUNTROWS(...)) → {{"op":"group","group_by":"agent","inner_agg":"count","value":null,"outer_agg":"mean"}}
    - mean win rate across agents → group_by "agent", inner_agg "mean" on a won flag, outer_agg "mean"
    - largest product share → group_by "product", inner_agg "share", outer_agg "max"
  - `new`: count of distinct `value_column` values whose FIRST occurrence is in the current period (first-time accounts/agents). Works only when a time dimension is resolved.

EXAMPLES:
{{"name": "Cycle Time by Stage",
  "prep": [{{"op": "derive.days_between", "start": "engage_date", "end": "close_date", "as": "cycle_days"}}],
  "steps": [{{"op": "group", "group_by": "deal_stage", "inner_agg": "mean", "value": "cycle_days", "outer_agg": "mean"}}],
  "compare": "pct_change", "unit": "days"}}

{{"name": "Largest Product Share",
  "steps": [{{"op": "group", "group_by": "product", "inner_agg": "share", "value": "revenue", "outer_agg": "max"}}],
  "compare": "pp_change", "unit": "ratio"}}

{{"name": "New Account Acquisition Rate",
  "steps": [{{"op": "new", "value_column": "account"}}],
  "compare": "pct_change", "unit": "count"}}

{{"name": "Product Concentration (top 20% of products)",
  "agg": "topk_share", "value_column": "revenue", "group_by": "product", "k": 0.2,
  "compare": "level", "unit": "ratio"}}

RULES:
- Pick FORM 1 when a single aggregate captures the metric; FORM 2 when it needs per-group breakdown, a derived column, first-time membership, or a top-k% cut.
- A `group` step REQUIRES all three fields: `group_by`, `inner_agg`, AND `outer_agg`. A missing `outer_agg` is invalid — always emit it.
- `compare` resolves the period-over-period comparison explicitly:
  - `level`: report the current-period value as-is (no delta).
  - `pct_change`: (current − prior) ÷ prior.
  - `pp_change`: current − prior, expressed in percentage points.
  - `rate_ratio`: current ÷ prior.
- Percentages are FRACTIONS: 0.17 = 17%, never 17.
- `condition` (and numerator/denominator `condition`) may reference the pre-filtered `df`; keep them simple and safe.
- `topk_share`: integer `k` = top-k members; a fraction like 0.2 = top 20% of members by value.
- `prep` output names must not collide with real columns.
- If a metric genuinely cannot be expressed by either form, OMIT it entirely — do not fabricate a spec.
- Use EXACT column names from the schema.

Output ONLY a JSON array. No code fences, no commentary.
