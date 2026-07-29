You are a strategy consultant defining a strategic performance measurement framework for a dataset.

SCHEMA:
{schema}

STRUCTURAL KNOWLEDGE GRAPH:
{structural_kg}

DIAGNOSTIC KNOWLEDGE GRAPH:
{diagnostic_kg}

=== YOUR TASK ===

Identify 3-5 key business priorities that this data can inform. For each priority, define a set of KPIs and supporting metrics that form a performance measurement framework — the kind of framework you would present to a business leader.

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

=== OUTPUT FORMAT ===

Return a JSON object:

{
  "priorities": [
    {
      "name": "Strategic priority name (e.g., Revenue Growth Trajectory, Profitability Evolution)",
      "description": "1 sentence describing what this priority covers in business terms",
      "focus_areas": "Brief hint about what to investigate — what dimensions and comparisons to explore",
      "kpis": [
        {
          "name": "KPI name — outcome measure describing the change, trajectory, or distribution (e.g., Revenue Growth Trajectory, Profit Margin Evolution, Revenue Concentration Index)",
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
          "influences": ["Name of the KPI(s) this metric explains or drives"]
        }
      ]
    }
  ]
}

=== RULES ===

- Each priority must have 1-3 KPIs and 5-10 supporting metrics
- Each supporting metric must influence at least one KPI (use the influences field)
- Use exact column names from the schema for the metric field
- KPI and metric names must be professional and descriptive — think "Revenue Growth Trajectory", "Profit Margin Evolution", "Segment Composition Shift", not "Revenue" or "Profit"
- Names should indicate the time dimension (Trajectory, Momentum, Trend, Evolution) or distribution lens (Concentration, Mix, Composition, Share)
- The measurement field must be a complete, precise business formula using business language (not code)
- Use the causal chains and dimensions_affecting from the DKG to determine which supporting metrics influence which KPIs
- Use the SKG entities, dimensions, and measures to identify meaningful metrics

EXAMPLE (e-commerce dataset):

{
  "priorities": [
    {
      "name": "Revenue Growth & Market Momentum",
      "description": "Assess top-line growth trajectory, decompose revenue drivers, and evaluate market position across segments",
      "focus_areas": "Revenue trends by region and category; volume vs. price decomposition; revenue concentration by customer segment",
      "kpis": [
        {
          "name": "Revenue Growth Trajectory",
          "metric": "Sales",
          "description": "Period-over-period revenue momentum identifying acceleration or deceleration, with seasonal baseline adjustment",
          "measurement": "(Current period Sales − Prior period Sales) ÷ Prior period Sales, computed quarterly with year-over-year comparison to account for seasonality"
        },
        {
          "name": "Revenue Concentration Index",
          "metric": "Sales",
          "description": "Measures dependency on top customer segments — rising concentration signals increased revenue volatility risk",
          "measurement": "Revenue share of top-3 customer segments relative to total revenue, tracked quarterly"
        }
      ],
      "supporting_metrics": [
        {
          "name": "Volume vs. Price Decomposition",
          "metric": "Quantity",
          "description": "Attribution of revenue change between volume effect and price effect to distinguish demand growth from pricing strategy",
          "measurement": "Revenue change = Volume change (Quantity × Price_prev) + Price change (Price × Quantity_prev), computed period-over-period",
          "influences": ["Revenue Growth Trajectory"]
        },
        {
          "name": "Segment Revenue Mix Shift",
          "metric": "Sales",
          "description": "Tracks composition change across customer segments — mix drift signals shifting demand patterns and revenue quality changes",
          "measurement": "Percentage point change in each segment's revenue contribution relative to prior period",
          "influences": ["Revenue Growth Trajectory", "Revenue Concentration Index"]
        },
        {
          "name": "Order Volume Trend",
          "metric": "Quantity",
          "description": "Unit volume trajectory as a leading indicator of revenue direction — volume declines precede revenue contraction",
          "measurement": "Period-over-period change in total units sold, with 3-period rolling average for trend smoothing",
          "influences": ["Revenue Growth Trajectory"]
        },
        {
          "name": "Average Order Value Trend",
          "metric": "Sales",
          "description": "Revenue per order as a measure of basket size evolution and upselling effectiveness",
          "measurement": "Total Sales ÷ Total Quantity, period-over-period comparison",
          "influences": ["Revenue Growth Trajectory"]
        },
        {
          "name": "Geographic Revenue Balance",
          "metric": "Sales",
          "description": "Revenue distribution across regions — unbalanced growth signals regional dependency and expansion opportunity",
          "measurement": "Revenue share by region and its percentage point change period-over-period",
          "influences": ["Revenue Concentration Index"]
        }
      ]
    },
    {
      "name": "Profitability & Margin Health",
      "description": "Analyze profit margin trajectory, identify margin drivers and pressure points, and assess sustainable profitability by segment",
      "focus_areas": "Profit margin trends by region, category, and customer segment; cost structure analysis; discount impact on margins",
      "kpis": [
        {
          "name": "Profit Margin Evolution",
          "metric": "Profit",
          "description": "Profitability trajectory distinguishing structural margin changes from transient effects",
          "measurement": "Profit ÷ Sales as percentage, tracked quarterly with year-over-year comparison to isolate trend from seasonality"
        }
      ],
      "supporting_metrics": [
        {
          "name": "Discount Intensity",
          "metric": "Discount",
          "description": "Average discount depth as a measure of pricing pressure — increasing discounts directly compress margins",
          "measurement": "Average discount percentage applied per order, period-over-period trend",
          "influences": ["Profit Margin Evolution"]
        },
        {
          "name": "Product-Level Margin Dispersion",
          "metric": "Profit",
          "description": "Variance in profit margins across product categories — wide dispersion signals optimization opportunity",
          "measurement": "Range and standard deviation of profit margin by category, period-over-period",
          "influences": ["Profit Margin Evolution"]
        },
        {
          "name": "Segment Profitability Divergence",
          "metric": "Profit",
          "description": "Profit margin trajectory across customer segments — diverging margins indicate structural mix shifts affecting overall profitability",
          "measurement": "Profit margin by customer segment, period-over-period comparison with spread analysis",
          "influences": ["Profit Margin Evolution"]
        }
      ]
    }
  ]
}

Return ONLY the JSON object. No other text.
