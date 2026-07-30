# AI Metric Knowledge Graph (v1)

## Store everything as files

```
metrics/
    revenue.md
    gross_margin.md
    discount.md
    orders.md

graphs/
    business_graph.json
    lineage_graph.json
    causal_graph.json

dashboards/
    ceo_dashboard.md
```

## Each metric is Markdown

```yaml
---
id: revenue
name: Revenue
owner: Finance
formula: SUM(net_sales)
tags:
  - growth
  - executive
---

# Revenue

Measures total realized sales after returns.

## Used by
- CEO Dashboard
- Board Report

## Business Notes
Revenue is primarily driven by:
- Orders
- Average Selling Price
- Customer Mix
```

## Graph JSON

```json
{
  "nodes": [
    {"id":"revenue","type":"metric"},
    {"id":"orders","type":"metric"},
    {"id":"discount","type":"metric"},
    {"id":"margin","type":"metric"},
    {"id":"profitability","type":"goal"}
  ],

  "edges":[
    {
      "from":"orders",
      "to":"revenue",
      "relation":"INFLUENCES"
    },
    {
      "from":"discount",
      "to":"orders",
      "relation":"INFLUENCES"
    },
    {
      "from":"discount",
      "to":"margin",
      "relation":"DECREASES"
    },
    {
      "from":"margin",
      "to":"profitability",
      "relation":"SUPPORTS"
    }
  ]
}
```

## Why separate Markdown and JSON?

Markdown = Human-readable documentation.

JSON = Machine-readable relationships.

The Markdown explains the metric. The graph enables AI reasoning.

## Evolution Path

Markdown + JSON  
↓  
Vector search (semantic retrieval)  
↓  
Knowledge graph traversal  
↓  
Graph database (Neo4j/Nebula/ArangoDB)  
↓  
AI business reasoning engine

Don't optimize too early. A few Markdown files plus one or more graph JSON files are enough to validate whether graph-based reasoning improves AI explanations.