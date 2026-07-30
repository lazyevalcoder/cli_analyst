# Analysis Reasoning Framework

This document guides how to think about data analysis questions. Use it as a mental model when reasoning through problems.

## Dataset Intent

This dataset captures business operations data. Common analysis goals:
- Performance measurement (how are we doing?)
- Trend identification (what's changing?)
- Comparison analysis (how do segments/regions compare?)
- Root cause investigation (why did something happen?)
- Forecasting preparation (what might happen next?)

## Analysis Personas

When answering questions, consider these perspectives:

### CFO (Chief Financial Officer)
- **Focus**: Profitability, ROI, cost control, margins
- **Key metrics**: Revenue, profit, margin %, cost per unit
- **Typical questions**: "Are we profitable?", "Where are costs highest?", "What's the ROI?"

### Sales Manager
- **Focus**: Pipeline, conversion, territory performance, quotas
- **Key metrics**: Sales volume, conversion rate, average deal size, quota attainment
- **Typical questions**: "Which region is performing best?", "What's our conversion rate?"

### Marketing Analyst
- **Focus**: Campaign performance, customer acquisition, segmentation
- **Key metrics**: CAC, LTV, conversion by channel, segment distribution
- **Typical questions**: "Which channel drives most sales?", "What's our customer profile?"

### Operations Manager
- **Focus**: Efficiency, throughput, inventory, supply chain
- **Key metrics**: Turnover rate, fulfillment time, stock levels
- **Typical questions**: "Are we efficient?", "What's our inventory health?"

## Analysis Strategies

### Strategy 1: Trend Analysis
**When to use**: Questions about change over time, growth, decline, patterns

**Trigger words**: "trend", "over time", "growth", "increase", "decrease", "compare years", "monthly", "quarterly", "yearly"

**Steps**:
1. ALWAYS check date range first (what period does data cover?)
2. Calculate the metric for the full period
3. Break down by time unit (month, quarter, year)
4. Compare periods (YoY, QoQ, MoM)
5. Identify inflection points or anomalies
6. Quantify the change (absolute and percentage)

**Code patterns**:
```python
# Check date range
print(f"Date range: {df['date'].min()} to {df['date'].max()}")

# Time-based aggregation
df.groupby(df['date'].dt.to_period('Q'))['metric'].sum()

# Period comparison
current = df[df['date'] >= cutoff]['metric'].sum()
previous = df[df['date'] < cutoff]['metric'].sum()
change = (current - previous) / previous * 100
```

---

### Strategy 2: Comparison Analysis
**When to use**: Questions about comparing segments, regions, categories, or any dimensional breakdown

**Trigger words**: "compare", "versus", "vs", "difference", "which is best", "which is worst", "rank", "top", "bottom", "highest", "lowest"

**Steps**:
1. Identify the comparison dimensions
2. Calculate the metric for each dimension value
3. Sort and rank
4. Calculate relative contributions (% of total)
5. Identify outliers or significant differences
6. Provide context (is the difference meaningful?)

**Code patterns**:
```python
# Dimensional breakdown
breakdown = df.groupby('dimension')['metric'].agg(['sum', 'mean', 'count'])

# Ranking
ranked = breakdown.sort_values('sum', ascending=False)

# Contribution analysis
ranked['pct_of_total'] = ranked['sum'] / ranked['sum'].sum() * 100
```

---

### Strategy 3: Distribution Analysis
**When to use**: Questions about spread, concentration, outliers, typical values

**Trigger words**: "distribution", "average", "median", "range", "outliers", "concentration", "most common", "typical"

**Steps**:
1. Calculate summary statistics (mean, median, std, min, max)
2. Identify the distribution shape (skewed, normal, bimodal)
3. Check for outliers (using IQR or z-score)
4. Calculate percentiles (25th, 50th, 75th, 90th)
5. Identify concentration (top 10% contribution)

**Code patterns**:
```python
# Summary statistics
df['metric'].describe()

# Percentiles
df['metric'].quantile([0.25, 0.5, 0.75, 0.9])

# Outlier detection (IQR method)
Q1 = df['metric'].quantile(0.25)
Q3 = df['metric'].quantile(0.75)
IQR = Q3 - Q1
outliers = df[(df['metric'] < Q1 - 1.5*IQR) | (df['metric'] > Q3 + 1.5*IQR)]
```

---

### Strategy 4: Composition Analysis
**When to use**: Questions about part-of-whole, contribution, makeup

**Trigger words**: "percentage", "proportion", "share", "contribution", "breakdown", "composition", "makeup"

**Steps**:
1. Calculate the total
2. Calculate each component's contribution
3. Express as percentage of total
4. Rank by contribution
5. Identify dominant components (>50% combined)
6. Check for concentration risk

**Code patterns**:
```python
# Composition
composition = df.groupby('category')['metric'].sum()
composition_pct = composition / composition.sum() * 100

# Pareto analysis (top 20% contributing 80%)
sorted_pct = composition_pct.sort_values(ascending=False)
cumulative = sorted_pct.cumsum()
top_20_pct = cumulative[cumulative <= 80].index
```

---

### Strategy 5: Diagnostic Analysis
**When to use**: Questions about why something happened, root cause, causal relationships

**Trigger words**: "why", "cause", "reason", "because", "due to", "impact", "factor", "correlation"

**Steps**:
1. State the observation clearly
2. Generate hypotheses (what could cause this?)
3. Test each hypothesis with data
4. Quantify the impact of each factor
5. Identify the primary driver
6. Validate with cross-checks

**Code patterns**:
```python
# Correlation analysis
df[['metric1', 'metric2', 'metric3']].corr()

# Segmented analysis (compare segments)
df.groupby('potential_factor')['outcome'].mean()

# Contribution to change
# (requires before/after data)
```

---

### Strategy 6: Ranking Analysis
**When to use**: Questions about best/worst, top/bottom N, leaderboards

**Trigger words**: "top", "bottom", "best", "worst", "highest", "lowest", "most", "least", "rank", "leaderboard"

**Steps**:
1. Identify what to rank (entities)
2. Identify the ranking metric
3. Calculate metric for each entity
4. Sort descending (or ascending for "worst")
5. Take top/bottom N
6. Add context (how far ahead/lagging?)

**Code patterns**:
```python
# Top N
df.groupby('entity')['metric'].sum().nlargest(10)

# Bottom N
df.groupby('entity')['metric'].sum().nsmallest(10)

# With context
ranked = df.groupby('entity')['metric'].sum().sort_values(ascending=False)
ranked['pct_of_top'] = ranked / ranked.iloc[0] * 100
```

## Universal Heuristics

Apply these regardless of question type:

### Always Check First
1. **Date range**: What period does the data cover?
2. **Record count**: How many rows? Is it a sample or full dataset?
3. **Null values**: Are there missing data that could skew results?
4. **Data types**: Are columns the expected type?

### Before Calculating
1. **Understand the grain**: What does each row represent?
2. **Check for duplicates**: Can metrics be double-counted?
3. **Verify assumptions**: Is "Sales" revenue or quantity?

### When Presenting Results
1. **Provide context**: Is this good? Bad? Normal?
2. **Quantify impact**: How much does this matter?
3. **Acknowledge limitations**: What might we be missing?
4. **Suggest next steps**: What should we investigate next?

## Common Analysis Patterns

### "What is X?" (Metric lookup)
→ Calculate and present the metric with context

### "How does X compare to Y?" (Comparison)
→ Use Comparison Analysis, quantify the difference

### "Why did X happen?" (Diagnostic)
→ Use Diagnostic Analysis, test hypotheses

### "What's the trend?" (Time series)
→ Use Trend Analysis, show the pattern

### "Show me the top/bottom N" (Ranking)
→ Use Ranking Analysis, provide context

### "What's the distribution?" (Statistical)
→ Use Distribution Analysis, show key statistics

### "What's the breakdown?" (Composition)
→ Use Composition Analysis, show contributions

## Question Decomposition

For complex questions, decompose into sub-questions:

**Example**: "Why did sales decline in Q4 compared to Q3, especially in the West region?"

Decomposition:
1. What was the overall sales change Q4 vs Q3?
2. How did each region perform Q4 vs Q3?
3. What specifically happened in the West region?
4. Which products/categories drove the West decline?
5. Were there any external factors (seasonality, etc.)?

Each sub-question maps to a strategy (Comparison, Trend, Diagnostic).

## Reasoning Checklist

Before executing code, confirm:

- [ ] I understand what the user is really asking
- [ ] I know which strategy fits this question
- [ ] I know which columns/measures to use
- [ ] I've considered the persona (if applicable)
- [ ] I have a clear plan for investigation
- [ ] I'll check basics first (date range, nulls, etc.)

## Adapting the Plan

The plan is a guide, not a contract. Adapt based on findings:
- If Step 1 reveals unexpected data, adjust Step 2
- If you find an interesting pattern, explore it
- If a step fails, try a different approach
- Stop early if you have enough information
- Add steps if you need more detail

The goal is a thorough answer, not rigid plan adherence.
