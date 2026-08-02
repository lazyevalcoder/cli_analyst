You are a BI analyst choosing ONE dimension to break a priority's metrics down by.

PRIORITY: {priority_name}
DESCRIPTION: {priority_description}

EXECUTIVE QUESTIONS:
{executive_questions}

METRICS (name: measurement):
{metric_names}

CANDIDATE DIMENSION COLUMNS (from the dataset schema; ONLY these are allowed, use the EXACT name):
{candidates}

Choose the ONE column whose per-member breakdown is most useful for THIS priority's business
question. Examples: a revenue-growth priority with a geographic angle -> a region column; a
segment-targeting priority -> a customer segment column; a logistics/fulfillment priority ->
a ship-mode column. Prefer lower cardinality when the choice is close.

Return a JSON object exactly like:
{"column": "<exact column name from the candidates>", "rationale": "<one-line business rationale>"}

Output ONLY the JSON object. No code fences, no commentary.
