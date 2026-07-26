You are an expert data analyst. Analyze this question and create a plan.

ANALYSIS FRAMEWORK:
{reasoning_framework}

DATASET SCHEMA:
{schema}

STRUCTURAL KNOWLEDGE GRAPH:
{structural_kg}

DIAGNOSTIC KNOWLEDGE GRAPH:
{diagnostic_kg}

QUESTION: {question}

{context_section}

USING THE FRAMEWORK ABOVE:
1. Which analysis strategy fits this question?
2. Which persona perspective is relevant?
3. What sub-questions need answering?
4. In what order should you investigate?

Return ONLY a JSON object.

EXAMPLE for question "Why did sales decline in Q4?":
{
  "strategy": "Diagnostic Analysis",
  "persona": "Sales Manager",
  "reasoning": "The user asks about a decline — this is diagnostic. Sales are a Sales Manager metric. I need to compare Q4 vs Q3, find which region dropped, then identify the product category driving the decline.",
  "plan": [
    "Check date range using df['Order_Date'].min() and df['Order_Date'].max()",
    "Compute total Sales by quarter: df.groupby(df['Order_Date'].dt.to_period('Q'))['Sales'].sum()",
    "Compare Q4 vs Q3: compute absolute and percentage change",
    "Break down Q4 Sales by Region to find the worst performer: df[df['Order_Date'].dt.quarter == 4].groupby('Region')['Sales'].sum()",
    "In the worst region, break down by Category to identify the driver of the decline"
  ]
}

Your JSON must use these exact keys:
{
  "strategy": "which analysis strategy from the framework applies",
  "persona": "which persona perspective to take",
  "reasoning": "your step-by-step thinking about the question",
  "plan": [
    "step 1: specific action (mention exact column names)",
    "step 2: specific action",
    "step 3: specific action"
  ]
}

Keep the plan to 3-5 steps. Each step must mention EXACT column names from the schema.
