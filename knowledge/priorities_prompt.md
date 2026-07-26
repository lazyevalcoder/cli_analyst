You are a strategy consultant. Given this dataset's schema and knowledge graphs, identify 3-5 key business priorities that this data can inform.

SCHEMA:
{schema}

STRUCTURAL KNOWLEDGE GRAPH:
{structural_kg}

DIAGNOSTIC KNOWLEDGE GRAPH:
{diagnostic_kg}

Think about what a business leader would care about most in this dataset.
For example: Revenue Growth, Profitability, Customer Retention, Cost Efficiency, Market Penetration, etc.

Return a JSON object:
{{
  "priorities": [
    {{
      "name": "Short priority name (e.g., Revenue Growth)",
      "description": "1 sentence describing what this priority covers",
      "key_metrics": ["Sales", "Profit"],
      "focus_areas": ["Brief hint about what to investigate for this priority — 1 sentence"]
    }}
  ]
}}

Return ONLY valid JSON. Keep descriptions sharp and business-focused.
Use exact column names from the schema for key_metrics.
