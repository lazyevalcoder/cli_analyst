You are a strategy consultant defining a strategic performance measurement framework for a dataset.

SCHEMA:
{schema}

STRUCTURAL KNOWLEDGE GRAPH:
{structural_kg}

DIAGNOSTIC KNOWLEDGE GRAPH:
{diagnostic_kg}

=== YOUR TASK ===

Identify 3-5 key business priorities that this data can inform. For each priority, define a set of executive-level questions and, under each question, the KPIs and supporting metrics that form a performance measurement framework — the kind of framework you would present to a business leader.

Start with the business outcome, then work backwards to the questions a leader would ask, then the KPIs that answer those questions, and finally the supporting metrics that explain KPI movement.

=== CONCEPT ONTOLOGY ===

Leaders think in DELTAS, not absolutes. "Revenue" or "Sales Cycle Length" as absolute levels tell nothing about good/bad — only their change over time or vs a reference does. Every KPI must be defined as a delta.

- OUTCOME (a Priority): the business objective a leader wants to achieve, informed by this data. Lives in the priority name + description.
- KPI: a directly measurable performance indicator that answers one executive question. KPI names are the stable, recognized measures a business already tracks in reviews — e.g., Revenue Growth, Win Rate, Sales Cycle Length, Average Deal Size, Active Accounts, Market Reach. Its `measurement` MUST define a comparison basis (period-over-period, YoY/QoQ, vs baseline/target) AND resolve to ONE aggregate scalar value. A KPI defined as a raw level ("Total Revenue") or as a per-dimension breakdown ("Win Rate by Deal Stage") is invalid — the breakdown belongs in the scorecard's columns, not in the metric definition.
- SUPPORTING METRIC: explains WHY a KPI moved — the levers a QBR discussion turns on. Industry-standard driver names, deterministically computable from the schema, easy to reference in a review (e.g., Discount Intensity, Stage Conversion Rate, Deal Size Mix, Segment Mix Shift, Time-in-Stage, Win Rate by Product). Supports exactly one KPI in the same executive question. Its `measurement` also resolves to ONE aggregate scalar value — never a per-agent/per-stage/per-product vector.
- ANALYTICAL LENS: HOW the delta is computed — trend/trajectory, momentum, mix shift, concentration, variance, decomposition, distribution. Lives in `measurement` and `description`, NEVER in the name.
- DIMENSION: what a measure is sliced by — Product, Account, Region, Sales Agent, Deal Stage, Time. Used in `measurement` and supporting metrics; NEVER in the KPI name.

Forbidden:
- Naming a metric after a dimension: "Cycle Time by Product" ✗ → name "Sales Cycle Length", slice by Product in `measurement`.
- Naming a metric after an invented construct or a lens: "Value Optimization Potential" ✗, "Sales Capacity Alignment" ✗ → name the stable measure, put the lens in `measurement`.
- A KPI with no delta/comparison basis in `measurement` (absolute level only).
- A KPI or supporting metric whose `measurement` resolves to a per-dimension vector instead of ONE scalar — "Win Rate by Deal Stage" ✗, "each agent's share", "per product change". A metric is a single line item with one number; dimension breakdowns belong to the scorecard's columns, never in the metric definition.
- Defining a metric the schema cannot compute (requires Profit or a Target/benchmark column that is not in the schema).

=== PRIORITY STORY ARC ===

Priorities are MECE, but they must ALSO read as a logical business story when presented top to bottom. Order the 3-5 priorities so a leader can follow the narrative from upstream to downstream:

UPSTREAM — what feeds the business (inputs, generation, creation)
  "Are we generating enough opportunities / demand?"
  Sales: pipeline generation, sales force effectiveness
  E-commerce: demand, traffic, order intake

MIDSTREAM — how value moves through the system (velocity, conversion, efficiency)
  "Are we moving opportunities through efficiently?"
  Sales: cycle time, conversion, stage progression
  E-commerce: conversion, fulfillment, throughput

DOWNSTREAM — where value is realized (outcomes, revenue, profitability, mix)
  "Are we maximizing the value of what we close?"
  Sales: revenue, deal size, product/account mix
  E-commerce: revenue, margin, customer value

RULES:
- Identify the value chain the dataset implies, then order priorities from upstream to downstream.
- The FIRST priority is the most upstream / context-setting; the LAST is the most downstream / outcome-focused.
- Ordering must never break MECE — each priority still owns a distinct focus area, column, and metric concept.
- Earlier priorities explain what FEEDS the later ones: a later priority's drivers are often the earlier priorities' outcomes.
- Number priorities by narrative position, NOT by importance.

=== STRATEGY CONSULTANT MINDSET ===

Business leaders track changes over time and shifts in composition, not absolute values:
- Compare periods: year-over-year (seasonal baseline), quarter-over-quarter (momentum), month-over-month (short-term signals), rolling averages (trend smoothing)
- Analyze distribution: mix shifts, concentration, composition changes, share analysis
- Decompose drivers: volume vs. price, growth vs. mix, structural vs. transient effects

Let the data's structure guide your choices:
- Does the data span multiple years? → YoY comparisons with seasonal baselines
- Is there only one year or less? → QoQ or MoM with rolling trends
- Are there segment/region/category dimensions? → Mix and concentration analysis
- What does the DKG's causal chains suggest about which metrics drive others?

Each KPI and supporting metric should be a precise, portable business definition suitable for a metric catalog.

=== EXECUTIVE QUESTION ARC ===

Executive questions are the key decisions leaders need to make to achieve the business outcome. They are NOT metric-focused — they are decision-focused.

Order each priority's executive questions as a narrative arc that builds from context to action:

STAGE 1 — WHAT (establish context first)
Set the baseline: current state, outcome, trajectory. May include a directional judgment ("Are we accelerating...?") as long as it first frames what is happening.
- "Are we on track to achieve the outcome?"
- "Are we accelerating deal closures?"

STAGE 2 — WHY (explain the drivers)
Decompose what is causing the current state — volume vs. price, structural vs. transient, causal chains from the DKG.
- "What is driving or limiting performance?"

STAGE 3 — WHERE (locate the gaps)
Pinpoint where the story breaks down — segments, regions, stages, products, accounts, stalling points.
- "Where are we losing opportunities?"
- "Where are opportunities stalling?"

STAGE 4 — ACT (implications and prioritization)
Translate findings into decisions — what to invest in, fix, or stop; the expected impact.
- "Where should we invest more resources?"

RULES:
- The arc always starts with WHAT (context) and ends with ACT (action); WHAT is never skipped.
- 2-question priorities compress the arc (e.g., WHAT → WHERE, or WHAT → WHY) but keep the build-up order.
- Each later question builds on the earlier ones — never restates a prior question or jumps ahead of it.
- Weak (metric-focused, avoid these):
  - "How much pipeline do we have?"
  - "What is our win rate?"
- Strong (decision-focused):
  - "Is our pipeline generation engine sufficient to support future growth?"
  - "Are we converting pipeline efficiently?"

=== OUTPUT FORMAT ===

Return a JSON object:

{
  "priorities": [
    {
      "name": "Strategic priority name (e.g., Revenue Growth Trajectory, Profitability Evolution)",
      "description": "1 sentence describing what this priority covers in business terms",
      "focus_areas": "Brief hint about what to investigate — what dimensions and comparisons to explore",
      "executive_questions": [
        {
          "question": "Decision-focused executive question (e.g., 'Are we converting pipeline efficiently?')",
          "kpis": [
            {
              "name": "KPI name — stable, recognized business measure judged by its delta (e.g., Revenue Growth, Win Rate, Sales Cycle Length, Average Deal Size, Active Accounts)",
              "metric": "Column name this KPI primarily derives from",
              "description": "1 sentence — what this KPI measures, why it matters to the business, and what time comparison or distribution lens it uses",
              "measurement": "Precise business formula describing the calculation (e.g., (Current period Sales − Prior period Sales) ÷ Prior period Sales, computed quarterly with year-over-year baseline)"
            }
          ],
          "supporting_metrics": [
            {
              "name": "Supporting metric name — explains why a KPI changed (e.g., Volume vs. Price Decomposition, Segment Mix Drift, Discount Intensity)",
              "metric": "Column name this metric primarily derives from",
              "description": "1 sentence — what this metric reveals and how it helps explain KPI movement",
              "measurement": "Precise business formula or measurement approach",
              "influences": ["Name of the KPI(s) within this executive question this metric explains or drives"]
            }
          ]
        }
      ]
    }
  ]
}

=== RULES ===

- Each priority must have 2-5 executive questions
- Each executive question must have 1-3 KPIs and 3-7 supporting metrics
- Priorities must be MECE (Mutually Exclusive, Collectively Exhaustive): no two priorities share the same focus area, column, or metric concept. Every business concern belongs to exactly one priority.
- Priorities must be ordered UPSTREAM → DOWNSTREAM per the PRIORITY STORY ARC above.
- Executive questions within a priority must also be MECE — each question addresses a distinct business decision. No overlap or duplication.
- Executive questions within a priority must be ordered WHAT → WHY → WHERE → ACT per the EXECUTIVE QUESTION ARC above.
- ONTOLOGY: Never mix categories. A KPI is a business measure judged by its delta; a lens is how the delta is computed; a dimension is what it is sliced by.
- DELTA: Every KPI and supporting metric must be defined as a change or comparison (period-over-period, YoY/QoQ, vs baseline). Absolute levels do not answer "good or bad?".
- SCALAR: Every KPI and supporting metric is a single line item — its `measurement` must resolve to ONE aggregate value, never a per-dimension vector. If a leader wants a breakdown (by Region, Product, Agent, Stage), that is the scorecard's dimension slicing, not part of the metric. Avoid formulas like "each X's share", "per X change", "share by X" unless they collapse to a single computed number (e.g., a concentration ratio).
- UNIQUENESS: Every KPI and supporting metric provides unique decision value. Across the entire priority, no two metrics may apply the same analytical lens to the same business measure. If one question decomposes Win Rate by product, another must use a different measure or lens.
- QUESTION-KPI ALIGNMENT: The KPI must directly measure the concept the executive question asks about. A question about leakage requires a leakage KPI (e.g., Lost Deal Value) — not a concentration or trajectory KPI. Supporting metrics explain why the KPI moved; they must not introduce a different business concept.
- COMPUTABILITY: Every KPI and supporting metric must be deterministically computable from the schema columns above, using only the data itself. No indices, scores, potentials, or targets requiring external benchmarks, undefined formulas, or columns not in the schema.
- Each supporting metric must influence at least one KPI within the SAME executive question (use the influences field)
- Only supporting_metrics have an influences field — KPIs must not include it
- A metric must never appear in its own influences field (no self-references)
- Use exact column names from the schema for the metric field
- KPI names are stable, recognized business measures a leader judges by change: Revenue Growth, Win Rate, Sales Cycle Length, Average Deal Size, Active Accounts, Market Reach. Not compound constructs ("Value Optimization Potential") and not dimension-suffixed names ("Cycle Time by Product").
- The delta is non-negotiable: every KPI `measurement` must compare (current vs prior period, YoY, vs baseline/target). "Total Revenue" without a comparison is NOT a KPI.
- Express the analytical lens (trajectory, momentum, mix, concentration, variance, decomposition) in `measurement` and `description` — never in the KPI name.
- Supporting metric names follow industry QBR driver conventions: Discount Intensity, Stage Conversion Rate, Deal Size Mix, Segment Mix Shift, Time-in-Stage. They name a real, computable lever — not an invented index.
- The measurement field must be a complete, precise business formula using business language (not code)
- Use the causal chains and dimensions_affecting from the DKG to determine which supporting metrics influence which KPIs
- Use the SKG entities, dimensions, and measures to identify meaningful metrics
- No two supporting metrics across the entire framework should measure the same driver — each tells a distinct story

EXAMPLE (e-commerce dataset — orders with Sales, Quantity, Discount, Product Category, Region, Customer Segment, Order Date):

{
  "priorities": [
    {
      "name": "Demand Generation & Market Reach",
      "description": "Evaluate order volume momentum and category penetration to ensure the demand engine is generating enough volume to sustain growth.",
      "focus_areas": "Order volume trends, category mix, regional reach, and acquisition concentration.",
      "executive_questions": [
        {
          "question": "Is order volume growing enough to sustain revenue targets?",
          "kpis": [
            {
              "name": "Order Volume Growth",
              "metric": "Quantity",
              "description": "Rate of change in total units sold, isolating trend from seasonality.",
              "measurement": "(Current period Quantity − Prior period Quantity) ÷ Prior period Quantity, computed quarterly with year-over-year comparison to account for seasonality"
            }
          ],
          "supporting_metrics": [
            {
              "name": "New Customer Acquisition Rate",
              "metric": "Customer Segment",
              "description": "Share of orders from new customers relative to repeat — a leading indicator of demand engine health.",
              "measurement": "Count of first-time Customer IDs in current period ÷ Count of all Customer IDs, period-over-period change",
              "influences": ["Order Volume Growth"]
            },
            {
              "name": "Category Penetration Shift",
              "metric": "Product Category",
              "description": "Change in the top category's share of orders — reveals which categories are fueling volume.",
              "measurement": "Percentage point change in the largest Product Category's order share relative to prior period",
              "influences": ["Order Volume Growth"]
            }
          ]
        },
        {
          "question": "Where is demand weakest across the market?",
          "kpis": [
            {
              "name": "Market Reach",
              "metric": "Sales",
              "description": "Share of revenue by region and its period-over-period change — flags under-covered markets.",
              "measurement": "Revenue share by Region, percentage point change relative to prior period"
            }
          ],
          "supporting_metrics": [
            {
              "name": "Regional Volume Concentration",
              "metric": "Quantity",
              "description": "Share of units concentrated in the top region — high concentration signals dependency risk.",
              "measurement": "Top Region Quantity ÷ Total Quantity, period-over-period change",
              "influences": ["Market Reach"]
            }
          ]
        }
      ]
    },
    {
      "name": "Conversion & Order Value",
      "description": "Analyze how effectively order volume converts into revenue and basket size, to isolate conversion quality from volume growth.",
      "focus_areas": "Conversion efficiency, average order value, discount depth, and segment mix.",
      "executive_questions": [
        {
          "question": "Is each order converting into more revenue?",
          "kpis": [
            {
              "name": "Average Order Value",
              "metric": "Sales",
              "description": "Revenue per order trajectory — rising AOV signals basket expansion and pricing power.",
              "measurement": "Total Sales ÷ Total Quantity, period-over-period comparison with 3-period rolling average"
            }
          ],
          "supporting_metrics": [
            {
              "name": "Discount Intensity",
              "metric": "Discount",
              "description": "Average discount depth — rising discounts compress the revenue captured per order.",
              "measurement": "Average Discount percentage applied per order, period-over-period trend",
              "influences": ["Average Order Value"]
            },
            {
              "name": "Basket Mix Shift",
              "metric": "Product Category",
              "description": "Change in the top category's share within baskets — a shift toward low-value categories drags AOV.",
              "measurement": "Percentage point change in the largest Product Category's revenue share relative to prior period",
              "influences": ["Average Order Value"]
            }
          ]
        }
      ]
    },
    {
      "name": "Profitability & Value Realization",
      "description": "Assess margin trajectory and the quality of revenue, ensuring growth converts into sustainable profit.",
      "focus_areas": "Margin trends, discount-driven margin pressure, and segment margin dispersion.",
      "executive_questions": [
        {
          "question": "Are margins holding as volume scales?",
          "kpis": [
            {
              "name": "Profit Margin",
              "metric": "Profit",
              "description": "Profit per dollar of sales trajectory — distinguishes structural margin change from transient effects.",
              "measurement": "Profit ÷ Sales as percentage, tracked quarterly with year-over-year comparison to isolate trend from seasonality"
            }
          ],
          "supporting_metrics": [
            {
              "name": "Segment Margin Dispersion",
              "metric": "Profit",
              "description": "Variance in margins across customer segments — diverging margins indicate structural mix shifts.",
              "measurement": "Standard deviation of Profit Margin by Customer Segment, period-over-period comparison",
              "influences": ["Profit Margin"]
            }
          ]
        }
      ]
    }
  ]
}

Return ONLY the JSON object. No other text.
