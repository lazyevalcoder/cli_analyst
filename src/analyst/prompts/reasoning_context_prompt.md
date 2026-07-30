You are a data analyst. Given this dataset schema and knowledge graphs, 
create a dataset-specific reasoning context. This will guide analysis of this specific dataset.

SCHEMA:
{schema}

STRUCTURAL KG:
{structural_kg}

DIAGNOSTIC KG:
{diagnostic_kg}

Create a concise dataset-specific context:

{
  "dataset_intent": "1-2 sentences describing what this dataset is about and its business purpose",
  "key_personas": [
    {"role": "analyst", "focus": "what this persona would care about in this dataset"}
  ],
  "analysis_focus": [
    "list 3-5 specific analysis areas relevant to this dataset"
  ],
  "key_questions": [
    "list 3-5 typical questions users would ask about this data"
  ]
}

Return ONLY the JSON object.
