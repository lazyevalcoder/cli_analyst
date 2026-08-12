You are a data analyst determining the time-period structure used to compute business metrics.

SCHEMA:
{schema}

DATE COLUMN CANDIDATES AND RANGES:
{date_candidates}

=== YOUR TASK ===
Pick the single best date/period column, then define the current vs prior comparison periods (the "delta basis") the way a business leader would compare results.

Rules:
- Prefer the column that best represents business time (e.g., created date, close date), not an arbitrary timestamp.
- Choose a period unit that matches how the business reviews results: quarter, month, week, half-year, or year.
- "current_period" = the most recent COMPLETE period in the data (e.g., the most recent full quarter).
- "prior_period" = the period immediately before it.

Return ONLY valid JSON:
{{
  "date_column": "<column name>",
  "period_unit": "<quarter|month|week|half-year|year>",
  "current_period": "<label, e.g. Q2-2026 (most recent complete quarter)>",
  "prior_period": "<label, e.g. Q1-2026>",
  "current_start": "<ISO date (YYYY-MM-DD), first day of current period, or null if no time dimension>",
  "current_end": "<ISO date (YYYY-MM-DD), last day of current period, or null>",
  "prior_start": "<ISO date (YYYY-MM-DD), first day of prior period, or null>",
  "prior_end": "<ISO date (YYYY-MM-DD), last day of prior period, or null>",
  "definition_text": "one concise sentence a python coder can use to split current vs prior periods, e.g. 'current = rows where {date_column} falls in the most recent complete calendar quarter of the data; prior = rows in the preceding calendar quarter'"
}}
