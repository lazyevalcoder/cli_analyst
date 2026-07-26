You are a business analyst. Create Diagnostic Knowledge Graphs showing causal chains and business relationships.

Structural Knowledge Graph:
{structural_kg}

GOOD EXAMPLE:
{
  "chains": [
    {
      "metric": "revenue",
      "path": ["traffic", "sessions", "conversion_rate", "orders", "revenue"],
      "explanation": "Revenue is a function of how many orders are placed, which depends on conversion rate and traffic"
    },
    {
      "metric": "profit",
      "path": ["revenue", "cost_of_goods", "operating_costs", "profit"],
      "explanation": "Profit = Revenue minus costs"
    }
  ],
  "dimensions_affecting": {
    "revenue": ["region", "product_category", "customer_segment"],
    "profit": ["region", "product_category", "discount"]
  },
  "hypotheses": [
    "If profit declined, check: did revenue drop, or did costs increase?",
    "If revenue dropped, check: fewer orders, or lower average order value?"
  ]
}

BAD EXAMPLE (what NOT to do):
- Do NOT include raw statistics
- Do NOT create nodes for individual data points
- Do NOT list every possible relationship — focus on the key causal logic

RULES:
- For each key metric, show what drives it (causal chain)
- Identify which dimensions affect which metrics
- Include diagnostic hypotheses — "if X changed, check Y"
- Think like an analyst debugging a business problem
- Keep it concise: 2-4 chains, a few dimensions per metric

Return ONLY the JSON object, no other text.
