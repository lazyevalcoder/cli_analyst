You are a data architect. Analyze this CSV schema and create a Structural Knowledge Graph.

{schema}

GOOD EXAMPLE (for an e-commerce dataset):
{
  "nodes": [
    {"id": "customer", "type": "entity", "label": "Customer"},
    {"id": "order", "type": "entity", "label": "Order"},
    {"id": "product", "type": "entity", "label": "Product"},
    {"id": "region", "type": "dimension", "label": "Region"},
    {"id": "category", "type": "dimension", "label": "Product Category"},
    {"id": "segment", "type": "dimension", "label": "Customer Segment"},
    {"id": "revenue", "type": "measure", "label": "Revenue"},
    {"id": "profit", "type": "measure", "label": "Profit"},
    {"id": "quantity", "type": "measure", "label": "Quantity"},
    {"id": "order_date", "type": "time", "label": "Order Date"}
  ],
  "edges": [
    {"source": "customer", "target": "order", "relation": "HAS_ORDER"},
    {"source": "order", "target": "product", "relation": "CONTAINS"},
    {"source": "region", "target": "customer", "relation": "ATTRIBUTE_OF"},
    {"source": "category", "target": "product", "relation": "ATTRIBUTE_OF"},
    {"source": "segment", "target": "customer", "relation": "ATTRIBUTE_OF"},
    {"source": "revenue", "target": "order", "relation": "MEASURE_OF"},
    {"source": "profit", "target": "order", "relation": "MEASURE_OF"},
    {"source": "quantity", "target": "order", "relation": "MEASURE_OF"},
    {"source": "order_date", "target": "order", "relation": "TEMPORAL_INDEX"}
  ]
}

BAD EXAMPLE (what NOT to do):
- Do NOT list every column as a separate node
- Do NOT include statistics (mean, median, etc.)
- Do NOT create nodes for individual values
- Do NOT include 50+ nodes — keep it focused on key entities

RULES:
- Group related columns into logical entities (e.g., Customer Name + Customer ID + Customer Segment → Customer entity)
- Identify measures (numeric aggregatable columns like Sales, Profit, Quantity)
- Identify dimensions (categorical columns that segment data like Region, Category)
- Identify time columns
- Create meaningful relationships: HAS_ORDER, CONTAINS, ATTRIBUTE_OF, MEASURE_OF, TEMPORAL_INDEX
- Keep it concise: 8-15 nodes is ideal

Return ONLY the JSON object, no other text.
