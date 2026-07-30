# AI-Native Metric Knowledge Graph

## Core Idea

A metric catalog should not just store metric definitions. It should be a **knowledge graph** where metrics are connected by different types of relationships. This enables AI to reason about the business instead of just looking up definitions.

## Node Types

- Metrics (Revenue, Gross Margin, CAC, Discount %)
    
- Dimensions (Region, Product, Customer)
    
- Datasets/Tables
    
- Dashboards
    
- Business Goals (Growth, Profitability)
    
- Owners (Finance, Sales, Marketing)
    

## Relationship Types

### 1. Data Lineage

Describes how a metric is computed.

- DERIVED_FROM
    
- CALCULATED_USING
    
- AGGREGATED_FROM
    

Example:  
Orders → Gross Revenue → Net Revenue

### 2. Business Hierarchy

Describes KPI decomposition.

- SUPPORTS
    
- PART_OF
    

Example:  
Growth  
├── Revenue  
├── Customers  
└── Retention

### 3. Causal Relationships

Describes business drivers.

- INFLUENCES
    
- INCREASES
    
- DECREASES
    

Example:  
Discount → Conversion → Orders → Revenue

Discount → Margin → Profitability

### 4. Correlation

Describes statistical relationships without implying causation.

- CORRELATED_WITH
    
- NEGATIVELY_CORRELATED_WITH
    

Include confidence and time lag.

### 5. Ownership

Describes governance.

- OWNED_BY
    
- STEWARD_OF
    

### 6. Consumption

Shows where metrics are used.

- USED_BY
    
- APPEARS_IN
    

Example:  
Revenue → CEO Dashboard

## Why this matters for AI

Instead of retrieving documentation, AI can traverse the graph.

Example:  
"Why did Revenue decline?"

AI traverses:  
Revenue  
← Orders  
← Conversion  
← Discount

It checks which connected metrics changed and explains:  
"Revenue decreased because lower discounts reduced conversion, leading to fewer orders. However, profitability improved because margins increased."

## Key Insight

A metric has multiple meanings simultaneously:

- It is **calculated from** data.
    
- It **supports** business goals.
    
- It is **influenced by** other metrics.
    
- It is **owned by** a team.
    
- It is **consumed by** dashboards.
    

Representing all these relationships as a graph creates an AI-native semantic layer capable of root cause analysis, impact analysis, KPI decomposition, and business reasoning.

## Long-Term Vision

Metric Catalog + Knowledge Graph + Time-Series Data + Lineage + AI

→ Business Knowledge Graph

This becomes the reasoning layer for AI-powered analytics, where AI answers _why_, _what changed_, _what is impacted_, and _what should I investigate next_ rather than simply returning metric definitions.