# RevOps Pipeline Dashboard Philosophy

> **A dashboard should not display metrics. It should answer questions.**
>
> The goal is to tell a story that helps an executive understand:
> **"Are we going to hit the plan? If not, why not?"**

---

# The Job of RevOps

RevOps exists to make the revenue engine:

- Predictable
- Efficient
- Scalable

Not to generate pipeline, but to ensure the entire revenue engine consistently produces the expected outcomes.

---

# The Dashboard Narrative

Instead of organizing by metric categories, organize by executive questions.

```
Revenue Goal (AOP)
        │
        ▼
1. Can we hit the number?
        │
        ▼
2. Do we have enough pipeline?
        │
        ▼
3. Is the pipeline healthy?
        │
        ▼
4. Is the pipeline moving?
        │
        ▼
5. Are we creating enough future pipeline?
        │
        ▼
6. Can leadership trust the forecast?
```

Every section answers one question.
Every answer naturally leads to the next question.

---

# Objective 1 — Hit Revenue

## Executive Question

**Are we going to hit our revenue target?**

## Objective

Understand whether revenue is at risk.

## North Star KPI

**Revenue Attainment Forecast**

## Supporting Metrics

- AOP
- Forecast
- Closed Won
- Commit
- Best Case
- Remaining Target
- Gap to Plan

## Decision

> Are we on track or off track?

---

# Objective 2 — Maintain Sufficient Pipeline

## Executive Question

**Do we have enough pipeline to hit the target?**

## Objective

Determine whether pipeline quantity is sufficient.

## North Star KPI

**Pipeline Coverage**

### Formula

Pipeline ÷ Remaining Target

(or AOP depending on business definition)

## Supporting Metrics

- Total Pipeline
- Qualified Pipeline
- Pipeline Coverage
- Coverage Trend
- Coverage by Segment
- Coverage by Region
- Coverage by Sales Team

## Decision

> Is this a pipeline quantity problem?

---

# Objective 3 — Improve Pipeline Quality

## Executive Question

**Can we trust this pipeline?**

## Objective

Ensure pipeline is healthy and realistic.

## North Star KPI

**Pipeline Health Score**

Possible inputs

- Stage balance
- Opportunity aging
- Qualification completeness
- Large deal concentration
- Average deal size
- Deal freshness

## Supporting Metrics

- Aging
- Stalled Opportunities
- Stage Distribution
- Deal Size Distribution
- Qualification %
- New vs Old Pipeline

## Decision

> Is the pipeline believable?

---

# Objective 4 — Improve Execution Efficiency

## Executive Question

**Is pipeline moving fast enough?**

## Objective

Improve pipeline flow.

## North Star KPI

**Pipeline Velocity**

Example Formula

(Pipeline × Win Rate × Avg Deal Size) ÷ Sales Cycle

## Supporting Metrics

- Stage Duration
- Stage Conversion
- Sales Cycle
- Win Rate
- Time in Stage
- Velocity Trend

## Decision

> Is execution slowing revenue?

---

# Objective 5 — Protect Future Revenue

## Executive Question

**Are we generating enough new pipeline?**

## Objective

Ensure future quarters are protected.

## North Star KPI

**Pipeline Generation vs Target**

## Supporting Metrics

- Pipeline Created
- Weekly Pipeline Creation
- Monthly Trend
- Pipeline by Source
- Pipeline by Marketing
- Pipeline by SDR
- Pipeline by AE
- Pipeline by Partner

## Decision

> Is enough new pipeline entering the system?

---

# Objective 6 — Increase Predictability

## Executive Question

**Can leadership trust the forecast?**

## Objective

Improve confidence in forecasting.

## North Star KPI

**Forecast Accuracy**

## Supporting Metrics

- Forecast Accuracy %
- Commit Accuracy
- Pipeline Slippage
- Push Rate
- Pull-ins
- Forecast Changes
- Quarter-over-Quarter Variance

## Decision

> Can executives rely on the forecast?

---

# Dashboard Flow

```
AOP
 │
 ▼
Forecast
 │
 ▼
Pipeline Coverage
 │
 ▼
Pipeline Health
 │
 ▼
Pipeline Velocity
 │
 ▼
Pipeline Generation
 │
 ▼
Forecast Accuracy
```

Each section should answer one question before moving to the next.

---

# Design Principles

### Don't build a metrics dashboard.

Build a **decision dashboard**.

Every chart should answer a question.

Every KPI should support a decision.

Every section should reduce uncertainty.

---

# One KPI Per Objective

| Objective | North Star KPI | Supporting Metrics |
|------------|----------------|--------------------|
| Hit Revenue | Revenue Forecast | Forecast, Closed Won, Commit, Gap |
| Maintain Pipeline | Pipeline Coverage | Pipeline $, Coverage Trend, Segment Coverage |
| Improve Quality | Pipeline Health Score | Aging, Stage Mix, Qualification, Deal Freshness |
| Improve Execution | Pipeline Velocity | Stage Duration, Conversion, Win Rate |
| Protect Future Revenue | Pipeline Generation | Created Pipeline, Source Mix, Creation Trend |
| Improve Predictability | Forecast Accuracy | Slippage, Push Rate, Commit Accuracy |

---

# The RevOps Diagnostic

A great pipeline dashboard should allow an executive to answer these questions in order:

1. Are we going to hit the number?
2. If not, do we have enough pipeline?
3. If yes, is the pipeline healthy?
4. If yes, is execution slowing us down?
5. If no, are we creating enough future pipeline?
6. Can we trust the forecast?

If these six questions can be answered in under five minutes, the dashboard is doing its job.

> **A dashboard is not a report.**
>
> **A dashboard is a conversation with the business.**
