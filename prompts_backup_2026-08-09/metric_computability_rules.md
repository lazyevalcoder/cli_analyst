# Metric Computability Rule Book

**A metric either works or it doesn't. There are no in-betweens.**
This rule book defines exactly which metric definitions the compute engine can and
cannot resolve. Every KPI and operational metric must pass ALL five tests before it
is proposed. If it fails any test, the metric is NOT defined — drop it or redefine it
in a way that passes.

The compute engine resolves each metric to ONE scalar per period using the schema and
the data alone. A metric is "computable" only when every rule below holds.

---

## THE FIVE TESTS

### 1. SCALAR — one number per period, never a vector
- The `measurement` must resolve to a single value for the current period and a single
  value for the prior period.
- `"Win Rate by Deal Stage"`, `"each agent's share"`, `"per product change"`, "a list of
  values" — these are vectors. NOT computable. A dimension breakdown belongs to a
  scorecard column, never to a metric definition.

### 2. COMPUTABLE — schema + data only, no outside knowledge
- Every referenced column must exist in the schema.
- No external benchmarks, targets, indices, scores, potentials, or hypothetical data.
- Example NOT computable: "pipeline coverage vs a 3x target" (target is external).

### 3. BASELINE — a delta needs a prior value that is real and non-zero
- `% change`, `% growth`, `% decline`, and `rate` (current ÷ prior) are ONLY defined
  when a prior window exists AND the prior value is a real, non-zero number.
- If you cannot be confident the prior value is non-zero, do NOT propose a delta. Define
  the metric at LEVEL (the current-period absolute value) instead, or do not define it.
- Rule of thumb: if the metric's meaning would collapse to "nothing before" (e.g.
  "new accounts this period" when the dataset may start exactly in the current window),
  a percentage is likely impossible — prefer the absolute count.
- The engine hard-fails deltas with a zero prior baseline. It will NEVER substitute a
  level where a percentage was requested.

### 4. ANCHOR — the counted rows must fall inside the time windows
- The period is anchored to ONE resolved time column (e.g. `close_date`). A metric's
  rows must be countable within the current/prior windows of that column.
- If the records you are counting carry NO date in that time column, they fall outside
  both windows and the metric computes to 0 vs 0 → a delta becomes undefined.
- Example NOT computable as a period-over-period delta: counting "active" records that
  have never closed and therefore have no `close_date`. That is a snapshot, not a
  window measure. Define it as a LEVEL snapshot, or drop it.
- If the metric's semantics need a DIFFERENT time column than the resolved period
  anchor, it cannot be compared period-over-period. Drop it or redefine it.

### 5. EXPRESSIBLE — maps to the operator DSL or a single aggregate
The spec must be one of the supported forms:

- FORM 1 — single aggregate:
  `agg` ∈ {count, sum, mean, median, std, count_distinct, ratio, share, topk_share},
  optional `condition`, optional `numerator`/`denominator`, `compare`, `unit`.
  - A `share` with no `value_column` is a COUNT share (numerator = count where condition,
    denominator = total count) — "share of orders using 'Express Air'" is expressible.
  - `agg` may reference a PREP derived column (e.g. `mean(cycle_days)`), so a scalar
    mean/median/sum over a date difference or derived arithmetic is expressible.
- FORM 2 — composed operators:
  - `prep`: derived columns — `derive.days_between`, `derive.year_of`,
    `derive.month_of`, `derive.arithmetic`. `derive.days_between` computes `end − start`;
    order the dates so the result is positive.
  - `steps`: `group` (inner_agg within each group, then outer_agg to one scalar; a
    `group_by: null` group step aggregates the whole frame to one scalar) and `new`
    (distinct values whose FIRST occurrence is in the current period, anchored to
    the resolved time column).
- `compare` ∈ {level, pct_change, pp_change, rate_ratio}. `custom` pandas code exists
  but is treated as high-risk and avoided unless nothing else fits.

EXPRESSIBLE shapes (the full routing surface — a measurement matching any of these IS
computable): count/condition; sum/mean/median/std/distinct-count with optional
condition; count-share and value-share; ratio of any two sub-aggregates; top-k /
top-k% concentration; first-time counts; per-group AVERAGEX-style outer aggregates;
whole-frame aggregates over a prep-derived column.

If the measurement cannot be expressed in Form 1 or Form 2, it is NOT defined.

---

## PER-METRIC SELF-CHECK (fill this in before proposing a metric)

For every KPI and operational metric you propose, you must be able to answer:

1. **Which schema column(s)?** (exact names, in the schema)
2. **Which aggregation?** (count / sum / mean / std / count_distinct / ratio / share /
   topk_share, or a group/new operator)
3. **Which comparison?** (level / pct_change / pp_change / rate_ratio)
4. **What is the prior baseline, and can I prove it is real and non-zero?**
   (if I cannot, the metric must be LEVEL, not a delta)
5. **Does every counted row fall inside the resolved time windows?**
   (if the rows have no date in the period's time column, the metric is a snapshot —
   LEVEL only, or drop it)

If you cannot answer every one of the five, do NOT emit the metric.

---

## THE CONTRACT

- Every KPI and operational metric is either **computed** (a real number) or
  **not computed** (an honest plain-language reason). No substituted values, no
  degraded versions, no "close enough" numbers.
- A metric that fails any test at definition time is dropped — it never reaches the
  compute engine, and never reaches the user as a broken-looking cell.
- The rule book is the single source of truth for what "computable" means. When in
  doubt, apply the five tests; when a test fails, do not define the metric.
