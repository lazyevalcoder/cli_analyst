You are a data analyst verifying computed metric values against their business intent.

SCHEMA:
{schema}

PERIOD DEFINITION (the current-vs-prior period every metric is computed over):
{period_definition}

For each metric you are given: the business `measurement` text, the `spec` used to compute it, the computed `value` (+ `unit`, `compare`), and a `samples` block of source rows for the columns the spec touches.

VERIFY ONE THING per metric: does the computed value faithfully match the measurement's intent AND look consistent with the sampled data?

Common failure to catch — SILENT BASIS SUBSTITUTION: the spec computes a different concept than the measurement describes but happens to be computable, so it returns a plausible-looking number. Examples:
- A "time in stage" / "stage velocity" / "stage stall" metric computed from overall close-to-engage cycle time (no per-stage timestamps exist).
- Several distinct measurements collapsed to the IDENTICAL win-rate value because each spec reduced to `won / total`.
- A "new" or "first-time" metric that degenerates to a plain distinct count because no prior history exists.
- A concentration/share metric that always returns 1.0 because the denominator equals the numerator.

Decide per metric:
- ok = true when the spec plausibly encodes the measurement and the value is consistent with the data.
- ok = false when the spec encodes a DIFFERENT concept than the measurement, the value is implausible, or several distinct metrics share the identical basis.

METRICS (JSON):
{metrics}

Return ONLY a JSON object keyed by exact metric name, e.g.:
{{
  "Metric Name": {{"ok": true, "note": "spec matches intent; value plausible"}},
  "Other Metric": {{"ok": false, "note": "computed from overall cycle time, not per-stage dwell"}}
}}

No code fences, no commentary. Every metric you received must appear in your output.
