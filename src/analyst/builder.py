import ast
import hashlib
import json
import logging
import math
import re
import warnings
from collections.abc import Callable
from datetime import datetime
from typing import cast

import pandas as pd

from src.analyst import llm, models, prompts, sandbox
from src.analyst.constants import (
    AGGS,
    COMPARES,
    COMPUTE_ENGINE_VERSION,
    DERIVE_OPS,
    INNER_AGGS,
    OUTER_AGGS,
    STATUS_COMPUTED,
    STATUS_ERROR,
    STATUS_NOT_COMPUTABLE,
    SUB_AGGS,
)
from src.analyst.graph import format_diagnostic_kg, format_structural_kg, slugify

logger = logging.getLogger(__name__)


def load_csv(path: str) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "windows-1252", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="latin-1")


def extract_column_info(df: pd.DataFrame) -> list[dict]:
    cols = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        if pd.api.types.is_numeric_dtype(df[col]):
            kind = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            kind = "datetime"
        else:
            kind = "text"
        unique = int(df[col].nunique())
        samples = [str(v) for v in df[col].dropna().head(3).tolist()]
        cols.append({"name": col, "dtype": dtype, "kind": kind, "unique": unique, "sample": samples})
    return cols


def build_schema_dict(df: pd.DataFrame) -> dict:
    columns = extract_column_info(df)
    sample_rows = []
    for _, row in df.head(5).iterrows():
        sample_rows.append({col: str(row[col]) for col in df.columns})
    return {"columns": columns, "rows": len(df), "sample_rows": sample_rows}


def extract_schema(df: pd.DataFrame) -> str:
    columns = extract_column_info(df)
    lines = [f"Table: {len(df)} rows × {len(df.columns)} columns", ""]
    lines.append("Columns:")
    for col in columns:
        sample_str = ", ".join(repr(s) for s in col["sample"])
        lines.append(f"  - {col['name']} ({col['dtype']}, {col['kind']}, {col['unique']} unique) sample: [{sample_str}]")

    lines.append("")
    lines.append("Sample rows:")
    for _, row in df.head(5).iterrows():
        vals = ", ".join(f"{col}={repr(str(row[col]))}" for col in df.columns)
        lines.append(f"  [{vals}]")

    return "\n".join(lines)


def _validate_structural_kg(kg: dict) -> dict:
    if not isinstance(kg, dict):
        return {"nodes": [], "edges": []}
    nodes = kg.get("nodes", [])
    edges = kg.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return {"nodes": [], "edges": []}
    return kg


def _validate_diagnostic_kg(kg: dict) -> dict:
    if not isinstance(kg, dict):
        return {"chains": [], "dimensions_affecting": {}, "hypotheses": []}
    chains = kg.get("chains", [])
    dims = kg.get("dimensions_affecting", {})
    hyps = kg.get("hypotheses", [])
    if not isinstance(chains, list):
        kg["chains"] = []
    if not isinstance(dims, dict):
        kg["dimensions_affecting"] = {}
    if not isinstance(hyps, list):
        kg["hypotheses"] = []
    return kg


def build_structural_kg(schema: str) -> dict:
    prompt = prompts.render("structural_kg_prompt.md", schema=schema)
    raw = llm.ask_json(prompt, system_context="You are a data architect. Return only valid JSON.")
    validated = _validate_structural_kg(raw)
    if not validated["nodes"] and not validated["edges"]:
        print("  ! LLM returned an empty or invalid structural KG. Expected nodes/edges describing the schema.")
        print("    Proceeding with an empty graph. `init` will continue but analysis quality will suffer.")
        return {"nodes": [], "edges": []}
    return validated


def build_diagnostic_kg(structural_kg: dict) -> dict:
    prompt = prompts.render("diagnostic_kg_prompt.md", structural_kg=str(structural_kg))
    raw = llm.ask_json(prompt, system_context="You are a business analyst. Return only valid JSON.")
    validated = _validate_diagnostic_kg(raw)
    if not validated.get("chains") and not validated.get("hypotheses"):
        print("  ! LLM returned an empty or invalid diagnostic KG. Expected causal chains and hypotheses.")
        print("    Proceeding with an empty graph. `analyze` will have less guidance for root-cause analysis.")
        return {"chains": [], "dimensions_affecting": {}, "hypotheses": []}
    return validated


def build_llm_context(structural_kg: dict, diagnostic_kg: dict) -> str:
    return (
        "=== STRUCTURAL KNOWLEDGE GRAPH (what exists in the data) ===\n"
        f"{format_structural_kg(structural_kg)}\n\n"
        "=== DIAGNOSTIC KNOWLEDGE GRAPH (causal relationships) ===\n"
        f"{format_diagnostic_kg(diagnostic_kg)}\n"
    )


def build_reasoning_context(schema: str, structural_kg: dict, diagnostic_kg: dict) -> dict:
    prompt = prompts.render(
        "reasoning_context_prompt.md",
        schema=schema,
        structural_kg=str(structural_kg),
        diagnostic_kg=str(diagnostic_kg),
    )
    return llm.ask_json(prompt, system_context="You are a data analyst. Return only valid JSON.")


def format_reasoning_context(context: dict) -> str:
    lines = ["=== Dataset Reasoning Context ===", ""]

    intent = context.get("dataset_intent", "")
    if intent:
        lines.append(f"Purpose: {intent}")
        lines.append("")

    personas = context.get("key_personas", [])
    if personas:
        lines.append("Key Personas:")
        for p in personas:
            lines.append(f"  - {p.get('role', '?')}: {p.get('focus', '')}")
        lines.append("")

    focus = context.get("analysis_focus", [])
    if focus:
        lines.append("Analysis Focus Areas:")
        for f in focus:
            lines.append(f"  - {f}")
        lines.append("")

    questions = context.get("key_questions", [])
    if questions:
        lines.append("Typical Questions:")
        for q in questions:
            lines.append(f"  - {q}")

    return "\n".join(lines)


def get_full_reasoning_framework(schema: str, structural_kg: dict, diagnostic_kg: dict) -> str:
    generic_framework = prompts.load_reasoning_framework()
    reasoning_context = build_reasoning_context(schema, structural_kg, diagnostic_kg)
    context_text = format_reasoning_context(reasoning_context)
    return f"{generic_framework}\n\n{context_text}"


def identify_priorities(schema: str, structural_kg: dict, diagnostic_kg: dict) -> dict:
    """Generate the strategic priority framework from schema + KGs.

    Returns a dict with `domain`, `health_indicators`, and `priorities` (the new
    outcome → executive questions → KPIs → operational metrics → lenses model).
    """
    prompt = prompts.render(
        "priorities_prompt.md",
        schema=schema,
        structural_kg=str(structural_kg),
        diagnostic_kg=str(diagnostic_kg),
    )
    raw = llm.ask_json(prompt, system_context="You are a strategy consultant. Return only valid JSON.")
    if not isinstance(raw, dict):
        return {"domain": "", "health_indicators": [], "priorities": []}
    priorities = raw.get("priorities", []) if isinstance(raw.get("priorities"), list) else []
    return {
        "domain": raw.get("domain", ""),
        "health_indicators": raw.get("health_indicators", []) if isinstance(raw.get("health_indicators"), list) else [],
        "priorities": priorities,
    }


def format_priority_metric_brief(pri: dict, diagnostic_kg: dict | None = None, values: dict | None = None) -> str:
    """Render a priority's KPIs + operational metrics (with DKG drill-down dimensions) as a prompt brief.

    If `values` (the per-priority stored values dict) is supplied, appends a PRE-COMPUTED VALUES section.
    Supports both the new model and legacy shapes.
    """
    eqs = pri.get("executive_questions", [])
    dims = diagnostic_kg.get("dimensions_affecting", {}) if isinstance(diagnostic_kg, dict) else {}
    dims_lower = {str(k).lower(): v for k, v in dims.items()}

    def drill_dims(metric_name: str, source_col: str) -> list:
        for key in (str(metric_name).lower(), slugify(metric_name), str(source_col).lower(), slugify(source_col)):
            if key in dims_lower:
                return dims_lower[key]
        return []

    def kpi_block(k, indent: str = "  ") -> list:
        col = k.get("metric", "")
        lines = [f"{indent}KPI: {k.get('name', '?')} (source: {col})"]
        if k.get("measurement"):
            lines.append(f"{indent}  Measurement: {k.get('measurement', '')}")
        dd = drill_dims(k.get("name", ""), col)
        if dd:
            lines.append(f"{indent}  Drill-down dimensions (from DKG): {', '.join(dd)}")
        lenses = k.get("analytical_lenses", [])
        if lenses:
            lines.append(f"{indent}  Analytical lenses: {', '.join(lenses)}")
        for op in k.get("operational_metrics", []):
            ocol = op.get("metric", "")
            lines.append(f"{indent}  OPERATIONAL: {op.get('name', '?')} (source: {ocol})")
            if op.get("measurement"):
                lines.append(f"{indent}    Measurement: {op.get('measurement', '')}")
        return lines

    lines = [f"PRIORITY: {pri.get('name', '')}", ""]
    if pri.get("description"):
        lines.append(f"OBJECTIVE: {pri.get('description', '')}")
        lines.append("")

    kpis = pri.get("kpis", [])
    if kpis:
        if isinstance(eqs, list) and eqs and not isinstance(eqs[0], dict):
            lines.append("EXECUTIVE QUESTIONS (framing):")
            for q in eqs:
                lines.append(f"  - {q}")
            lines.append("")
        for k in kpis:
            lines.extend(kpi_block(k))
            lines.append("")
    else:
        eq_objs = [e for e in eqs if isinstance(e, dict)]
        for i, eq in enumerate(eq_objs, 1):
            lines.append(f"EXECUTIVE QUESTION {i}: {eq.get('question', '?')}")
            for k in eq.get("kpis", []):
                lines.extend(kpi_block(k, "  "))
            for s in eq.get("supporting_metrics", []):
                col = s.get("metric", "")
                lines.append(f"  SUPPORTING: {s.get('name', '?')} (source: {col})")
                if s.get("measurement"):
                    lines.append(f"    Measurement: {s.get('measurement', '')}")
            lines.append("")
        for k in pri.get("kpis", []):
            lines.extend(kpi_block(k))
            lines.append("")
        for s in pri.get("supporting_metrics", []):
            col = s.get("metric", "")
            lines.append(f"  SUPPORTING: {s.get('name', '?')} (source: {col})")
            if s.get("measurement"):
                lines.append(f"    Measurement: {s.get('measurement', '')}")
            lines.append("")

    if values:
        lines.append("PRE-COMPUTED VALUES:")
        for mname, rec in values.items():
            if not isinstance(rec, dict):
                continue
            value = rec.get("value")
            unit = rec.get("unit", "")
            period = rec.get("period", "")
            status = rec.get("status", "")
            verified = rec.get("verified", False)
            if status == STATUS_NOT_COMPUTABLE:
                reason = rec.get("reason_display") or friendly_reason(rec.get("reason", ""))
                lines.append(f"  {mname}: NOT COMPUTED — {reason}")
                continue
            line = f"  {mname}: value={value} {unit}".rstrip()
            if period:
                line += f" | period: {period}"
            line += f" | status: {status}"
            line += " | verified" if verified else " | UNVERIFIED"
            lines.append(line)
        lines.append("")
    return "\n".join(lines).rstrip()


def generate_briefing(schema: str, structural_kg: dict, diagnostic_kg: dict, priorities: list) -> dict:
    prompt = prompts.render(
        "briefing_prompt.md",
        schema=schema,
        structural_kg=str(structural_kg),
        diagnostic_kg=str(diagnostic_kg),
        priorities=str(priorities),
    )
    raw = llm.ask_json(prompt, system_context="You are a strategy consultant. Return only valid JSON.")
    if not isinstance(raw, dict):
        return {"priority_insights": [], "suggested_questions": []}
    return raw


# ---------------------------------------------------------------------------
# Priority values (three-tier split): fingerprints, period, compute, interpret
# ---------------------------------------------------------------------------


def _iter_priority_metrics(pri: dict):
    """Yield (kind, metric) for every KPI and operational metric in a priority.

    Delegates to the shared traversal in `models` so all three priority shapes are
    handled in exactly one place.
    """
    yield from models.iter_priority_metrics(pri)


def priority_fingerprint(pri: dict) -> str:
    """Definition fingerprint: sha256 over the sorted (name, measurement) pairs."""
    pairs = sorted((str(k.get("name", "")), str(k.get("measurement", ""))) for _, k in _iter_priority_metrics(pri))
    payload = json.dumps(pairs, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_DATE_NAME_HINTS = (
    "date",
    "time",
    "month",
    "quarter",
    "year",
    "day",
    "period",
    "created",
    "updated",
    "modified",
    "timestamp",
    "dt",
)
_DATE_SAMPLE_PATTERNS = (
    re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"),  # ISO / YYYY-MM-DD
    re.compile(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"),  # US-style MM/DD/YYYY
    re.compile(r"\d{4}[-/.]\d{1,2}$"),  # YYYY-MM
)


def _looks_like_date_column(df: pd.DataFrame, col: str) -> bool:
    if any(h in str(col).lower() for h in _DATE_NAME_HINTS):
        return True
    samples = df[col].dropna().astype(str).head(50)
    if len(samples) == 0:
        return False
    matches = sum(1 for v in samples if any(p.search(v) for p in _DATE_SAMPLE_PATTERNS))
    return matches / len(samples) >= 0.5


def _detect_date_columns(df: pd.DataFrame) -> list[str]:
    cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    if cols:
        return cols
    for c in df.columns:
        if df[c].dtype == object and _looks_like_date_column(df, c):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    s = pd.to_datetime(df[c], errors="coerce")
                if s.notna().mean() > 0.8 and (s.max() - s.min()).days > 0:
                    cols.append(c)
            except Exception as e:
                logger.debug("date-coerce failed for column %r: %s", c, e)
                continue
    return cols


def data_fingerprint(df: pd.DataFrame) -> str:
    """Data fingerprint: sha256 of shape + latest date value — catches data reloads."""
    cols = _detect_date_columns(df)
    max_date = None
    if cols:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                max_date = str(pd.to_datetime(df[cols[0]], errors="coerce").max())
        except Exception as e:
            logger.debug("could not fingerprint latest date: %s", e)
            max_date = None
    payload = f"{df.shape}|{max_date}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _period_for(d, unit: str):
    """Return (start, end) as dates of the `unit` period containing date `d`."""
    import calendar
    from datetime import date as _date
    from datetime import timedelta as _timedelta

    if unit == "week":
        sunday = d - _timedelta(days=(d.weekday() + 1) % 7)
        return sunday - _timedelta(days=6), sunday
    if unit == "month":
        start = _date(d.year, d.month, 1)
        end = _date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        return start, end
    if unit == "quarter":
        q_start_month = ((d.month - 1) // 3) * 3 + 1
        start = _date(d.year, q_start_month, 1)
        end_month = q_start_month + 2
        end = _date(d.year, end_month, calendar.monthrange(d.year, end_month)[1])
        return start, end
    if unit == "half-year":
        end_month = 12 if d.month >= 7 else 6
        start = _date(d.year, 1 if end_month == 6 else 7, 1)
        end = _date(d.year, end_month, calendar.monthrange(d.year, end_month)[1])
        return start, end
    if unit == "year":
        return _date(d.year, 1, 1), _date(d.year, 12, 31)
    return d, d


def _period_bounds(unit: str | None, max_date) -> dict | None:
    """Deterministic most-recent-complete-period bounds.

    Returns {"current_start", "current_end", "prior_start", "prior_end"} as ISO
    date strings (inclusive), or None if they cannot be derived. Used as a fallback
    when the LLM omits machine-readable bounds.
    """
    if not max_date or pd.isna(max_date):
        return None
    from datetime import timedelta as _timedelta

    d = pd.Timestamp(max_date).date()
    unit = (unit or "quarter").lower()

    cur_start, cur_end = _period_for(d, unit)
    if cur_end > d:
        # most recent complete period is the one before the (incomplete) current one
        cur_end = cur_start - _timedelta(days=1)
        cur_start, cur_end = _period_for(cur_end, unit)
    if cur_end > d:
        return None
    prior_end = cur_start - _timedelta(days=1)
    prior_start, _ = _period_for(prior_end, unit)
    return {
        "current_start": cur_start.isoformat(),
        "current_end": cur_end.isoformat(),
        "prior_start": prior_start.isoformat(),
        "prior_end": prior_end.isoformat(),
    }


def resolve_period(df: pd.DataFrame, schema_str: str) -> dict:
    """Resolve the canonical current-vs-prior period ONCE per compute run."""
    cols = _detect_date_columns(df)
    if not cols:
        return {
            "date_column": None,
            "period_unit": None,
            "current_period": None,
            "prior_period": None,
            "current_start": None,
            "current_end": None,
            "prior_start": None,
            "prior_end": None,
            "definition_text": "No time dimension detected; compute each metric over the ENTIRE dataset (no current/prior split).",
        }
    samples = {}
    for c in cols:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = pd.to_datetime(df[c], errors="coerce").dropna()
        if len(s):
            samples[c] = {"min": str(s.min()), "max": str(s.max())}
    prompt = prompts.render(
        "priority_period_prompt.md",
        schema=schema_str,
        date_candidates=str(samples),
    )
    raw = llm.ask_json(prompt, system_context="You are a data analyst. Return only valid JSON.", label="Resolving time period")
    if not isinstance(raw, dict):
        raw = {}
    date_col = raw.get("date_column")
    if date_col not in df.columns:
        date_col = cols[0]
    definition = raw.get("definition_text")
    if not definition:
        definition = (
            f"current = rows where {date_col} falls in the most recent complete "
            f"calendar period of the data; prior = rows in the preceding period."
        )
    else:
        definition = definition.replace("{date_column}", str(date_col))
        definition = definition.replace("{date_col}", str(date_col))

    # Machine-readable bounds: prefer the LLM's, fall back to deterministic.
    bounds = {
        "current_start": raw.get("current_start"),
        "current_end": raw.get("current_end"),
        "prior_start": raw.get("prior_start"),
        "prior_end": raw.get("prior_end"),
    }
    if not _valid_bounds(bounds):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = pd.to_datetime(df[date_col], errors="coerce").dropna()
        bounds = _period_bounds(raw.get("period_unit"), s.max() if len(s) else None) or {}

    return {
        "date_column": date_col,
        "period_unit": raw.get("period_unit"),
        "current_period": raw.get("current_period"),
        "prior_period": raw.get("prior_period"),
        "current_start": bounds.get("current_start"),
        "current_end": bounds.get("current_end"),
        "prior_start": bounds.get("prior_start"),
        "prior_end": bounds.get("prior_end"),
        "definition_text": definition,
    }


def _valid_bounds(bounds: dict) -> bool:
    from datetime import datetime as _dt

    vals = [bounds.get(k) for k in ("current_start", "current_end", "prior_start", "prior_end")]
    if any(v is None for v in vals):
        return False
    try:
        cs, ce, ps, pe = (_dt.fromisoformat(cast(str, v)) for v in vals)
    except (ValueError, TypeError):
        return False
    return cs <= ce and ps <= pe and pe < cs


def _parse_compute_output(output: str) -> dict:
    """Parse the single printed JSON line into {metric_name: {value, unit, basis}}."""
    if not output:
        return {}
    m = re.search(r"\{.*\}", output, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


_BLOCKED_IN_CONDITION = ("import", "__", "open(", "exec(", "eval(", "compile(", "os.", "sys.")

# Residual pre-filter: only DATA-LIMITED measurements are hard-filtered now. Per-group /
# by / top-% / distinct / new measurements are expressible via the operator DSL and flow
# to the LLM. These need per-row stage-entry/transition history the current grain lacks.
_DATA_LIMITED_PATTERNS = (
    re.compile(r"\btime[\s-]?in[\s-]?stage\b", re.I),
    re.compile(r"\bstage[\s-]?(entry|transition|history|dwell)\b", re.I),
    re.compile(r"\bvelocity\s+through\s+stages?\b", re.I),
    re.compile(r"\b(advancing|progressing)\s+(?:to|into|through)\s+(?:the\s+)?next\s+stage\b", re.I),
    re.compile(r"\bstage\s+progression\b", re.I),
    re.compile(r"\bstage[\s-]to[\s-]stage\b", re.I),
    re.compile(r"\b(days?|time)\s+(?:spent\s+)?(?:in|per|within)\s+stage\b", re.I),
)
_DATA_LIMITED_PRIMITIVE = "requires stage-entry/transition timestamps"


def _non_scalar_reason(measurement: str) -> tuple[str, str]:
    """Classifier for measurements the operator DSL cannot express.

    Returns (reason, missing_primitive); both '' when the measurement is expressible and
    should flow to the LLM. Hard-filtering is now reserved for DATA-LIMITED cases (e.g.
    true dwell time needs stage-entry timestamps); the missing_primitive value feeds the
    operator backlog.
    """
    text = str(measurement or "")
    for pat in _DATA_LIMITED_PATTERNS:
        m = pat.search(text)
        if m:
            return (
                f"measurement requires per-row stage-entry/transition timestamps that "
                f"the current data grain does not provide "
                f'(matched "{m.group(0).strip()}")',
                _DATA_LIMITED_PRIMITIVE,
            )
    return "", ""


# ---------------------------------------------------------------------------
# Computability rule book — plain-language reasons + data-aware pre-check.
# Philosophy: a metric either computes or it is honestly NOT computed. No
# substituted values, no degraded versions, no jargon leaking to users.
# ---------------------------------------------------------------------------

_FRIENDLY_REASON_MAP = [
    (
        re.compile(r"no prior-period baseline \(prior value is 0\)", re.I),
        "There is no earlier period to compare against — the prior value is zero, so a percentage change can't be computed.",
    ),
    (
        re.compile(r"prior comparison period contains no data|prior period.*no data|no data.*prior period", re.I),
        "The prior comparison period has no data, so a period-over-period change can't be computed.",
    ),
    (
        re.compile(r"no time dimension|no time column|no prior period \(no time", re.I),
        "The data has no time column, so period-over-period metrics can't be computed.",
    ),
    (
        re.compile(r"metric omitted or not produced in output", re.I),
        "This metric couldn't be expressed in a form the compute engine supports, so it was not computed.",
    ),
    (
        re.compile(r"LLM could not express this measurement as a scalar spec", re.I),
        "This metric couldn't be expressed in a form the compute engine supports, so it was not computed.",
    ),
    (re.compile(r"no valid spec produced", re.I), "No valid computation definition could be produced for this metric."),
    (
        re.compile(r"template returned null", re.I),
        "The metric's formula returned no value — for example, an empty prior period or a division by zero.",
    ),
    (
        re.compile(r"division by zero|divide by zero|empty prior period", re.I),
        "The calculation had nothing to divide by, so no value can be produced.",
    ),
    (
        re.compile(r"requires per-row stage-entry/transition timestamps", re.I),
        "This metric needs per-stage timing data (entry/transition timestamps) that this dataset doesn't contain.",
    ),
    (re.compile(r"not in schema|unknown column|not a column", re.I), "This metric references a column that isn't in the data."),
    (re.compile(r"malformed value record", re.I), "The computed result was malformed, so no value could be recorded."),
    (re.compile(r"script failed", re.I), "The computation hit an error and could not produce a value."),
    (re.compile(r"no value produced", re.I), "No value could be produced for this metric."),
]


def friendly_reason(reason) -> str:
    """Translate a technical not-computed reason into plain business language."""
    if not reason:
        return ""
    text = str(reason)
    for pat, msg in _FRIENDLY_REASON_MAP:
        if pat.search(text):
            return msg
    return text


_DELTA_LANGUAGE_PATTERNS = (
    re.compile(r"\b(percentage|pct|%)[\s-]*change\b", re.I),
    re.compile(r"\b(change|growth|decline|shrink)\b.*\b(rate|percent|pct|%)\b", re.I),
    re.compile(r"\b(versus|vs\.?|compared to|relative to)\s+(the\s+)?prior\b", re.I),
    re.compile(r"\b(period-over-period|qoq|yoy|mom|over the prior|from the prior)\b", re.I),
)


def _is_delta_measurement(text: str) -> bool:
    return any(p.search(text) for p in _DELTA_LANGUAGE_PATTERNS)


def _precheck_measurement(measurement: str, period: dict, df: pd.DataFrame = None) -> tuple[str, str]:
    """Data-aware gate from the rule book (BASELINE / ANCHOR), run before any LLM call.

    Returns (reason, missing_primitive); both '' when the measurement should flow to
    the LLM. Only deterministic, provable cases are hard-filtered here — everything
    else flows to the spec generator and the runtime guard.
    """
    reason, prim = _non_scalar_reason(measurement)
    if reason:
        return reason, prim
    text = str(measurement or "")
    if not _is_delta_measurement(text):
        return "", ""
    if not period.get("date_column") or not period.get("prior_start"):
        return (
            "the dataset has no time dimension to compare against — period-over-period metrics cannot be computed",
            "no prior period (no time dimension)",
        )
    if df is not None and period.get("date_column") and period.get("prior_start") and period.get("prior_end"):
        col = period["date_column"]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                s = pd.to_datetime(df[col], errors="coerce").dropna()
            has_prior = bool(((s >= pd.Timestamp(period["prior_start"])) & (s <= pd.Timestamp(period["prior_end"]))).any())
        except Exception as e:
            logger.debug("prior-period presence check failed, assuming present: %s", e)
            has_prior = True
        if not has_prior:
            return (
                "the prior comparison period contains no data, so a period-over-period change cannot be computed",
                "empty prior period",
            )
    return "", ""


def _parse_specs(raw) -> list[dict]:
    """Normalize the LLM spec output into a list of spec dicts."""
    if isinstance(raw, dict):
        for key in ("specs", "metrics", "results"):
            v = raw.get(key)
            if isinstance(v, list):
                return [s for s in v if isinstance(s, dict)]
        out = []
        for k, v in raw.items():
            if isinstance(v, dict):
                if not v.get("name"):
                    v = dict(v, name=k)
                out.append(v)
        return out
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, dict)]
    return []


def _check_expression(expr: str, columns: set) -> tuple[bool, str]:
    """Validate an L2 derive.arithmetic expression: AST-safe, and every bare name is a
    known column (or derived name)."""
    if any(b in expr for b in _BLOCKED_IN_CONDITION):
        return False, f"derive.arithmetic expr contains a blocked token: {expr[:60]}"
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False, f"derive.arithmetic expr does not compile: {expr[:60]}"
    msg = sandbox.check_ast_safe(tree)
    if msg:
        return False, f"derive.arithmetic expr not safe: {msg}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in columns:
            return False, f"derive.arithmetic references unknown name '{node.id}'"
    return True, ""


class _ColumnRefRewriter(ast.NodeTransformer):
    """Rewrite every bare name in an expression to df['name'] for template emission."""

    def visit_Name(self, node):
        return ast.Subscript(
            value=ast.Name(id="df", ctx=ast.Load()),
            slice=ast.Constant(value=node.id),
            ctx=node.ctx,
        )


def _rewrite_expr(expr: str) -> str:
    tree = ast.parse(expr, mode="eval")
    tree = _ColumnRefRewriter().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _validate_spec(spec: dict, columns: set, batch_names: set | None = None) -> tuple[bool, str]:
    name = spec.get("name")
    if not name:
        return False, "spec missing name"
    compare = spec.get("compare")
    if compare not in COMPARES:
        return False, f"unknown compare '{compare}'"

    # ---- shared helpers ----
    def check_cond(c):
        if not c:
            return True, ""
        if not isinstance(c, str):
            return False, "condition is not a string"
        if any(b in c for b in _BLOCKED_IN_CONDITION):
            return False, f"condition contains a blocked token: {c[:60]}"
        try:
            compile(c, "<cond>", "eval")
        except SyntaxError:
            return False, f"condition does not compile: {c[:60]}"
        return True, ""

    def check_sub(sub, role):
        if not isinstance(sub, dict):
            return False, f"{role} is not an object"
        if sub.get("agg") not in SUB_AGGS:
            return False, f"{role} agg must be count|sum|mean|count_distinct, got {sub.get('agg')}"
        col = sub.get("value_column")
        if sub.get("agg") in ("sum", "mean", "count_distinct") and col not in columns:
            return False, f"{role} value_column '{col}' not in schema"
        return check_cond(sub.get("condition"))

    # ---- prep (L2 derived columns, shared per EQ) ----
    derived: set = set()
    prep = spec.get("prep") or []
    if prep:
        if not isinstance(prep, list):
            return False, "prep must be an array"
        for op in prep:
            if not isinstance(op, dict):
                return False, "prep op is not an object"
            opn = op.get("op")
            if opn not in DERIVE_OPS:
                return False, f"unknown prep op '{opn}'"
            asname = op.get("as")
            if not asname or not isinstance(asname, str):
                return False, "prep op missing 'as' output name"
            if asname in columns:
                return False, f"prep output '{asname}' collides with a real column"
            if asname in derived:
                return False, f"prep output '{asname}' declared twice"
            if opn == "derive.days_between":
                for key in ("start", "end"):
                    if op.get(key) not in columns:
                        return False, f"prep {opn} {key} '{op.get(key)}' not in schema"
            elif opn in ("derive.year_of", "derive.month_of"):
                if op.get("column") not in columns:
                    return False, f"prep {opn} column '{op.get('column')}' not in schema"
            elif opn == "derive.arithmetic":
                expr = op.get("expr")
                if not isinstance(expr, str) or not expr.strip():
                    return False, "prep derive.arithmetic missing expr"
                ok, msg = _check_expression(expr, columns | derived)
                if not ok:
                    return False, msg
            derived.add(asname)

    # ---- operator DSL steps vs legacy single agg vs custom ----
    steps = spec.get("steps")
    agg = spec.get("agg")
    kind = spec.get("kind")

    if kind == "custom":
        if agg is not None or steps is not None:
            return False, "custom spec must not also define agg/steps"
        code = spec.get("code")
        if not isinstance(code, str) or not code.strip():
            return False, "custom spec missing code"
        if any(b in code for b in _BLOCKED_IN_CONDITION):
            return False, "custom code contains a blocked token"
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False, "custom code does not compile"
        unsafe = sandbox.check_ast_safe(tree)
        if unsafe:
            return False, f"custom code not safe: {unsafe}"
    elif steps is not None:
        if agg is not None:
            return False, "spec must use 'agg' OR 'steps', not both"
        if not isinstance(steps, list) or not steps:
            return False, "steps must be a non-empty array"
        for step in steps:
            if not isinstance(step, dict):
                return False, "step is not an object"
            opn = step.get("op")
            if opn == "group":
                gcol = step.get("group_by")
                if gcol is not None and gcol not in columns and gcol not in derived:
                    return False, f"group step group_by '{gcol}' not in schema"
                inner = step.get("inner_agg")
                if inner not in INNER_AGGS:
                    return False, f"group step inner_agg must be one of {sorted(INNER_AGGS)}, got {inner}"
                val = step.get("value")
                if inner != "count" and val not in columns and val not in derived:
                    return False, f"group step value '{val}' not in schema"
                outer = step.get("outer_agg")
                if outer is None:
                    outer = "mean"
                    step["outer_agg"] = "mean"
                if outer not in OUTER_AGGS:
                    return False, f"group step outer_agg must be one of {sorted(OUTER_AGGS)}, got {outer}"
            elif opn == "new":
                if step.get("value_column") not in columns:
                    return False, f"new step value_column '{step.get('value_column')}' not in schema"
            else:
                return False, f"unknown step op '{opn}'"
    elif agg is None:
        if spec.get("input_ref"):
            pass  # input_ref composes an existing measure; no agg/steps needed
        else:
            return False, "spec must use 'agg' or 'steps' (or kind='custom')"
    else:
        if agg not in AGGS:
            return False, f"unknown agg '{agg}'"
        if agg in ("sum", "mean", "median", "std", "topk_share", "count_distinct"):
            col = spec.get("value_column")
            if col not in columns and col not in derived:
                return False, f"value_column '{col}' not in schema"
        if agg in ("ratio", "share"):
            if agg == "ratio":
                for role in ("numerator", "denominator"):
                    ok, msg = check_sub(spec.get(role), role)
                    if not ok:
                        return False, msg
            else:  # share: denominator may be inferred from value_column total
                if spec.get("denominator") is not None:
                    ok, msg = check_sub(spec.get("denominator"), "denominator")
                    if not ok:
                        return False, msg
                if spec.get("numerator") is not None:
                    ok, msg = check_sub(spec.get("numerator"), "numerator")
                    if not ok:
                        return False, msg
        if agg == "topk_share":
            if spec.get("group_by") not in columns:
                return False, f"group_by '{spec.get('group_by')}' not in schema"
            k = spec.get("k")
            if isinstance(k, bool):
                return False, f"topk_share k must be a positive int or a fraction in (0,1], got {k}"
            if isinstance(k, int) and k < 1:
                return False, f"topk_share k must be a positive int, got {k}"
            if isinstance(k, float) and not (0 < k <= 1):
                return False, f"topk_share fractional k must be in (0,1], got {k}"
            if k is None or not isinstance(k, (int, float)):
                return False, f"topk_share k must be a positive int or a fraction in (0,1], got {k}"

    # ---- composition: input_ref ----
    ref = spec.get("input_ref")
    if ref is not None:
        if not isinstance(ref, str) or not ref:
            return False, "input_ref must be a metric name"
        if batch_names is not None and ref not in batch_names:
            return False, f"input_ref '{ref}' not in this metric group"
        if compare != "level":
            return False, "input_ref only supports compare='level' in this version"

    ok, msg = check_cond(spec.get("condition"))
    if not ok:
        return False, msg
    if not spec.get("unit"):
        return False, "spec missing unit"
    return True, ""


def _sel_block(mask_var: str, sub: dict, out_var: str) -> list[str]:
    """Emit lines computing one aggregate `out_var` from `df[mask_var]` per sub-spec."""
    lines = [f"    _sel = df[{mask_var}]"]
    cond = sub.get("condition")
    if cond:
        lines.append(f"    _sel = _sel[{cond}]")
    agg = sub.get("agg")
    if agg == "count":
        lines.append(f"    {out_var} = float(len(_sel))")
    elif agg == "count_distinct":
        col = sub.get("value_column")
        lines.append(f"    {out_var} = float(_sel[{col!r}].nunique())")
    else:
        col = sub.get("value_column")
        lines.append(f"    _v_ser = _sel[{col!r}]")
        if agg == "sum":
            lines.append(f"    {out_var} = float(_v_ser.sum())")
        elif agg == "mean":
            lines.append(f"    {out_var} = float(_v_ser.mean())")
        elif agg == "median":
            lines.append(f"    {out_var} = float(_v_ser.median())")
        else:  # std
            lines.append(f"    {out_var} = float(_v_ser.std())")
    return lines


def _final_value(compare: str, cur_var: str, pri_var: str, out_var: str) -> list[str]:
    lines = []
    if compare == "level":
        lines.append(f"    {out_var} = {cur_var}")
    elif compare == "pct_change":
        lines.append(
            f"    {out_var} = (({cur_var} - {pri_var}) / {pri_var}) if ({pri_var} is not None and {pri_var} != 0) else None"
        )
    elif compare == "pp_change":
        lines.append(f"    {out_var} = ({cur_var} - {pri_var}) if ({cur_var} is not None and {pri_var} is not None) else None")
    elif compare == "rate_ratio":
        lines.append(f"    {out_var} = ({cur_var} / {pri_var}) if ({pri_var} is not None and {pri_var} != 0) else None")
    return lines


def _emit_group_step(lines: list[str], mask_var: str, step: dict, out_var: str) -> None:
    gcol = step.get("group_by")
    val = step.get("value")
    inner = step.get("inner_agg")
    outer = step.get("outer_agg")
    if gcol is None:
        if inner == "count":
            lines.append(f"    _g = pd.Series([float(len(df.loc[{mask_var}]))])")
        elif inner == "share":
            lines.append("    _g = pd.Series([1.0])")
        else:
            lines.append(f"    _g = pd.Series([df.loc[{mask_var}][{val!r}].agg({inner!r})])")
        lines.append("    if _g.isna().any():")
        lines.append(f"        {out_var} = None")
        lines.append("    else:")
        lines.append(f"        {out_var} = float(_g.agg({outer!r}))")
        return
    if inner == "count":
        lines.append(f"    _g = df.loc[{mask_var}].groupby({gcol!r}).size()")
    elif inner == "share":
        lines.append(f"    _g = df.loc[{mask_var}].groupby({gcol!r})[{val!r}].sum()")
        lines.append("    _tot_g = _g.sum()")
        lines.append("    if len(_g) == 0 or _tot_g != _tot_g or _tot_g == 0:")
        lines.append(f"        {out_var} = None")
        lines.append("    else:")
        lines.append("        _g = _g / _tot_g")
        lines.append(f"        {out_var} = float(_g.agg({outer!r}))")
        return
    else:
        lines.append(f"    _g = df.loc[{mask_var}].groupby({gcol!r})[{val!r}].agg({inner!r})")
    lines.append("    if len(_g) == 0:")
    lines.append(f"        {out_var} = None")
    lines.append("    else:")
    lines.append(f"        {out_var} = float(_g.agg({outer!r}))")


def _emit_new_step(lines: list[str], mask_var: str, step: dict, out_var: str, bound_date) -> None:
    if not bound_date:
        lines.append(f"    {out_var} = None")
        return
    col = step.get("value_column")
    lines.append(f"    _in_period = set(df.loc[{mask_var}][{col!r}].dropna().astype(str))")
    lines.append(f"    _seen_before = set(df.loc[_DT < pd.Timestamp({bound_date!r})][{col!r}].dropna().astype(str))")
    lines.append(f"    {out_var} = float(len(_in_period - _seen_before))")


def _emit_period_value(lines: list[str], mask_var: str, spec: dict, period: dict, out_var: str) -> None:
    """Append lines computing ONE period's scalar into `out_var` (v1 agg or v2 steps)."""
    if spec.get("kind") == "custom":
        for line in str(spec.get("code", "")).strip().splitlines():
            lines.append("    " + line)
        return
    if spec.get("input_ref"):
        lines.append(f"    {out_var} = _out[{json.dumps(spec.get('input_ref'))}]['value']")
        return
    steps = spec.get("steps")
    if steps:
        bound_date = period.get("current_start") if mask_var == "_CUR" else period.get("prior_start")
        for step in steps:
            if step.get("op") == "group":
                _emit_group_step(lines, mask_var, step, out_var)
            elif step.get("op") == "new":
                _emit_new_step(lines, mask_var, step, out_var, bound_date)
        return

    agg = spec.get("agg")
    if agg in ("count", "sum", "mean", "median", "std", "count_distinct"):
        lines += _sel_block(
            mask_var, {"agg": agg, "value_column": spec.get("value_column"), "condition": spec.get("condition")}, out_var
        )
    elif agg in ("ratio", "share"):
        vcol = spec.get("value_column")
        if agg == "share" and vcol is None:
            num = spec.get("numerator") or {"agg": "count", "condition": spec.get("condition")}
            den = spec.get("denominator") or {"agg": "count", "condition": None}
        else:
            num = spec.get("numerator") or {"agg": "sum", "value_column": vcol, "condition": spec.get("condition")}
            den = spec.get("denominator")
            if den is None and agg == "share":
                den = {"agg": "sum", "value_column": vcol, "condition": None}
        lines += _sel_block(mask_var, num, "_n")
        lines += _sel_block(mask_var, den, "_d")
        lines.append(f"    {out_var} = (_n / _d) if (_d is not None and _d != 0) else None")
    else:  # topk_share
        gcol = spec.get("group_by")
        col = spec.get("value_column")
        k = spec.get("k")
        lines.append(f"    _g = df.loc[{mask_var}].groupby({gcol!r})[{col!r}].sum()")
        lines.append("    if len(_g) == 0:")
        lines.append(f"        {out_var} = None")
        lines.append("    else:")
        lines.append("        _tot = _g.sum()")
        lines.append("        _sh = _g / _tot if _tot else _g * 0.0")
        if isinstance(k, float):
            lines.append(f"        _n = max(int(math.ceil(len(_g) * {k})), 1)")
            lines.append(f"        {out_var} = float(_sh.nlargest(_n).sum())")
        else:
            kk = int(k or 5)
            lines.append(f"        {out_var} = float(_sh.nlargest({kk}).sum())")


def _emit_prep(lines: list[str], specs: list[dict]) -> None:
    """Emit one shared prep block (union of all specs' prep ops, deduped by output name).
    Each op is guarded so a failed derive only drops metrics that depend on it."""
    seen = set()
    for spec in specs:
        for op in spec.get("prep") or []:
            asname = op.get("as")
            if asname in seen:
                continue
            seen.add(asname)
            opn = op.get("op")
            lines.append("\ntry:")
            if opn == "derive.days_between":
                lines.append(
                    f"    df[{json.dumps(asname)}] = ((pd.to_datetime(df[{json.dumps(op['end'])}], errors='coerce')"
                    f" - pd.to_datetime(df[{json.dumps(op['start'])}], errors='coerce')).dt.days)"
                )
            elif opn == "derive.year_of":
                lines.append(
                    f"    df[{json.dumps(asname)}] = pd.to_datetime(df[{json.dumps(op['column'])}], errors='coerce').dt.year"
                )
            elif opn == "derive.month_of":
                lines.append(
                    f"    df[{json.dumps(asname)}] = pd.to_datetime(df[{json.dumps(op['column'])}], errors='coerce').dt.month"
                )
            elif opn == "derive.arithmetic":
                expr = _rewrite_expr(op.get("expr"))
                lines.append(f"    df[{json.dumps(asname)}] = ({expr})")
            lines.append("except Exception:")
            lines.append("    pass")


def build_metric_script(specs: list[dict], period: dict) -> str:
    """Deterministic template: turns specs + the shared period into one executable script.

    No LLM in the execution path. Each metric is wrapped in its own try/except so a
    bad value only drops that metric, never the whole run. `prep` derived columns are
    computed once per run (each op guarded) and shared by all metrics.
    """
    date_col = period.get("date_column")
    lines = ["_out = {}"]
    if date_col:

        def _get(key: str):
            return period.get(key)

        lines.append("_DT = pd.to_datetime(df[_DT_COL], errors='coerce')")
        # swapped in below
        lines = [line.replace("_DT_COL", repr(date_col)) for line in lines]
        cur_lo, cur_hi = _get("current_start"), _get("current_end")
        pri_lo, pri_hi = _get("prior_start"), _get("prior_end")
        if cur_lo and cur_hi and pri_lo and pri_hi:
            lines.append(f"_CUR = (_DT >= pd.Timestamp({cur_lo!r})) & (_DT <= pd.Timestamp({cur_hi!r}))")
            lines.append(f"_PRI = (_DT >= pd.Timestamp({pri_lo!r})) & (_DT <= pd.Timestamp({pri_hi!r}))")
        else:
            lines.append("_CUR = pd.Series(True, index=df.index)")
            lines.append("_PRI = pd.Series(False, index=df.index)")
    else:
        lines.append("_CUR = pd.Series(True, index=df.index)")
        lines.append("_PRI = pd.Series(False, index=df.index)")

    _emit_prep(lines, specs)

    for spec in specs:
        name = str(spec.get("name", ""))
        if not name:
            continue
        compare = spec.get("compare", "level")
        lines.append("\ntry:")
        _emit_period_value(lines, "_CUR", spec, period, "_c")
        if compare != "level":
            _emit_period_value(lines, "_PRI", spec, period, "_p")
        lines += _final_value(compare, "_c", "_p", "_v")
        lines.append("    if _v is None or _v != _v:  # NaN check")
        lines.append("        _v = None")
        if compare in ("pct_change", "rate_ratio"):
            lines.append("    if _v is None and _p is not None and _p == 0:")
            lines.append('        _vr = "no prior-period baseline (prior value is 0)"')
            lines.append("    else:")
            lines.append("        _vr = None")
        else:
            lines.append("    _vr = None")
        basis_expr = 'f"current {_c:.3g}"' if compare == "level" else 'f"current {_c:.3g} vs prior {_p:.3g}"'
        lines.append(
            f"    _out[{json.dumps(name)}] = {{'value': _v, 'unit': {json.dumps(str(spec.get('unit', '')))}, 'basis': {basis_expr}, 'null_reason': _vr}}"
        )
        lines.append("except Exception:")
        lines.append("    pass")

    lines.append("\nprint(json.dumps(_out, ensure_ascii=False))")
    return "\n".join(lines)


def _nc_record(period: dict, measurement: str, reason: str, missing_prim: str | None = None, spec=None, basis="", unit=""):
    """Build a not_computable value record with both a technical `reason` and a
    plain-language `reason_display` (rule book: honest statuses, no jargon)."""
    rec = {
        "filters": [],
        "value": None,
        "unit": unit,
        "basis": basis,
        "period": period["current_period"],
        "measurement": measurement,
        "spec": spec,
        "verified": False,
        "status": STATUS_NOT_COMPUTABLE,
        "reason": reason,
        "reason_display": friendly_reason(reason),
    }
    if missing_prim:
        rec["missing_primitive"] = missing_prim
    return rec


def _computed_record(period: dict, measurement: str, value, unit: str, basis: str, spec: dict) -> dict:
    """Build a computed value record (the partner of `_nc_record`)."""
    rec = {
        "filters": [],
        "value": value,
        "unit": unit,
        "basis": basis,
        "period": period["current_period"],
        "measurement": measurement,
        "spec": spec,
        "verified": False,
        "status": STATUS_COMPUTED,
    }
    return rec


# ---- Dimension breakdowns (metrics in rows, dimension members in columns) ----
# Reuses each computed metric's stored `spec` and the trusted executor: for a given
# dimension, a per-member table of {current, prior, delta} is produced deterministically.


def _mask_lines(period: dict) -> list[str]:
    """Script lines defining `_CUR`/`_PRI` boolean masks from the period's date column."""
    date_col = period.get("date_column")
    lines = []
    if date_col:
        lines.append(f"_DT = pd.to_datetime(df[{date_col!r}], errors='coerce')")
        cur_lo, cur_hi = period.get("current_start"), period.get("current_end")
        pri_lo, pri_hi = period.get("prior_start"), period.get("prior_end")
        if cur_lo and cur_hi and pri_lo and pri_hi:
            lines.append(f"_CUR = (_DT >= pd.Timestamp({cur_lo!r})) & (_DT <= pd.Timestamp({cur_hi!r}))")
            lines.append(f"_PRI = (_DT >= pd.Timestamp({pri_lo!r})) & (_DT <= pd.Timestamp({pri_hi!r}))")
        else:
            lines.append("_CUR = pd.Series(True, index=df.index)")
            lines.append("_PRI = pd.Series(False, index=df.index)")
    else:
        lines.append("_CUR = pd.Series(True, index=df.index)")
        lines.append("_PRI = pd.Series(False, index=df.index)")
    return lines


def _build_cell_script(spec: dict, period: dict) -> str:
    """One execution computing a metric's RAW current and prior scalars over whatever
    df is passed (compare-agnostic), plus per-window row counts so a member with no rows
    in a window is distinguishable from a real zero baseline. Used per member."""
    lines = ["_out = {}"] + _mask_lines(period)
    _emit_prep(lines, [spec])
    lines.append("_out['_cur_n'] = int(len(df[_CUR]))")
    lines.append("_out['_pri_n'] = int(len(df[_PRI]))")
    lines.append("try:")
    _emit_period_value(lines, "_CUR", spec, period, "_c")
    lines.append("    _out['_cur'] = _c")
    _emit_period_value(lines, "_PRI", spec, period, "_p")
    lines.append("    _out['_pri'] = _p")
    lines.append("except Exception:")
    lines.append("    pass")
    lines.append("print(json.dumps(_out, ensure_ascii=False))")
    return "\n".join(lines)


def _apply_compare(compare: str, cur, pri):
    """Mirror of `_final_value`: the final metric value from raw per-period scalars."""
    if compare == "level":
        return cur
    if cur is None or pri is None:
        return None
    if compare == "pct_change":
        return (cur - pri) / pri if pri != 0 else None
    if compare == "pp_change":
        return cur - pri
    if compare == "rate_ratio":
        return cur / pri if pri != 0 else None
    return None


def _cell_verified(sub, period: dict, spec: dict, delta, unit: str) -> bool:
    """Per-member cell verification: L1 re-derivation when the spec is recomputable,
    otherwise L0 plausibility. Mirrors `_verify_layers` on the member subset."""
    try:
        if _recomputable_spec(spec):
            expected = _recompute_value(sub, period, spec)
            if expected is None:
                return False
            return _close(expected, delta)
    except Exception as e:
        logger.debug("cell L1 re-derivation failed: %s", e)
        pass
    ok, _ = _check_value({"value": delta, "unit": unit, "spec": spec})
    return ok


def _breakdown_cell(sub, period: dict, spec: dict, mrec: dict) -> dict:
    """One member cell: run the metric's spec on the member subset and return the
    {current, prior, delta} record. Honest `not_computable` when data or a baseline
    is missing for that member (rule book: no substituted values)."""
    compare = spec.get("compare", "level")
    unit = str(spec.get("unit") or mrec.get("unit") or "")
    cur = pri = None
    try:
        code = _build_cell_script(spec, period)
        ok, out = sandbox.execute_code(code, sub)
        parsed = _parse_compute_output(out) if ok else {}
        cur, pri = parsed.get("_cur"), parsed.get("_pri")
        if parsed.get("_cur_n") == 0:
            cur = None
        if parsed.get("_pri_n") == 0:
            pri = None
    except Exception as e:
        logger.debug("breakdown cell compute failed for %r: %s", spec.get("name"), e)
        cur = pri = None
    delta = _apply_compare(compare, cur, pri)
    if cur is not None:
        basis = f"current {cur:.3g}" if (compare == "level" or pri is None) else f"current {cur:.3g} vs prior {pri:.3g}"
    else:
        basis = ""
    if delta is None:
        if cur is None:
            reason = "no rows for this member in the current period"
        elif pri is None:
            reason = "no rows for this member in the prior period"
        else:
            reason = "no prior-period baseline (prior value is 0)"
        return {
            "current": cur,
            "prior": pri,
            "delta": None,
            "unit": unit,
            "basis": basis,
            "status": STATUS_NOT_COMPUTABLE,
            "verified": False,
            "reason": reason,
            "reason_display": friendly_reason(reason),
        }
    return {
        "current": cur,
        "prior": pri,
        "delta": delta,
        "unit": unit,
        "basis": basis,
        "status": STATUS_COMPUTED,
        "verified": _cell_verified(sub, period, spec, delta, unit),
    }


def _dimension_members(df, col: str) -> list[str]:
    """Sorted distinct non-null member values of a dimension column."""
    return sorted(str(v) for v in df[col].dropna().astype(str).unique())


def _categorical_dimension_candidates(df, period: dict, max_cardinality: int = 50, min_coverage_rows: int = 1) -> list[dict]:
    """Deterministic candidate dimension columns: text-typed, low-to-moderate
    cardinality, with rows in BOTH the current and prior windows. Sorted by data
    coverage (desc) then cardinality (asc) so the fallback pick is the most-backed."""
    date_col = period.get("date_column")
    cur_mask = pri_mask = None
    if date_col and date_col in df.columns:
        try:
            _dt = pd.to_datetime(df[date_col], errors="coerce")
            if period.get("current_start") and period.get("current_end"):
                cur_mask = (_dt >= pd.Timestamp(period["current_start"])) & (_dt <= pd.Timestamp(period["current_end"]))
            if period.get("prior_start") and period.get("prior_end"):
                pri_mask = (_dt >= pd.Timestamp(period["prior_start"])) & (_dt <= pd.Timestamp(period["prior_end"]))
        except Exception as e:
            logger.debug("dimension-window mask build failed: %s", e)
            cur_mask = pri_mask = None
    candidates = []
    for col in df.columns:
        if col == date_col:
            continue
        s = df[col]
        if pd.api.types.is_numeric_dtype(s.dtype) or pd.api.types.is_datetime64_any_dtype(s.dtype):
            continue
        nonnull = s.notna()
        uniq = s.dropna().astype(str).nunique()
        if uniq < 2 or uniq > max_cardinality:
            continue
        if cur_mask is not None and pri_mask is not None:
            cur_n = int((nonnull & cur_mask).sum())
            pri_n = int((nonnull & pri_mask).sum())
            if cur_n < min_coverage_rows or pri_n < min_coverage_rows:
                continue
            coverage = cur_n + pri_n
        else:
            coverage = int(nonnull.sum())
            if coverage < min_coverage_rows:
                continue
        candidates.append({"column": col, "unique": int(uniq), "coverage": coverage})
    candidates.sort(key=lambda c: (-c["coverage"], c["unique"], c["column"]))
    return candidates


def suggest_breakdown_dimensions(pri: dict, df: pd.DataFrame, schema_str: str, period: dict) -> dict | None:
    """One LLM call choosing ONE breakdown dimension for the priority, restricted to
    categorical schema columns with data in both windows. An invalid or absent LLM pick
    falls back to the top data-backed candidate — never a fabricated column."""
    candidates = _categorical_dimension_candidates(df, period)
    if not candidates:
        return None
    cand_names = [c["column"] for c in candidates]
    cand_lines = "\n".join(f"  - {c['column']} ({c['unique']} distinct values)" for c in candidates)
    metric_lines = "\n".join(f"  - {k.get('name', '')}: {k.get('measurement', '')}" for _, k in _iter_priority_metrics(pri))
    eq = pri.get("executive_questions") or []
    prompt = prompts.render(
        "dimension_suggestion_prompt.md",
        priority_name=pri.get("name", ""),
        priority_description=pri.get("description", ""),
        executive_questions="\n".join(f"  - {q}" for q in eq),
        metric_names=metric_lines,
        candidates=cand_lines,
    )
    pick = None
    try:
        raw = llm.ask_json(prompt, system_context="You are a BI analyst. Return ONLY a JSON object.")
        pick = raw[0] if isinstance(raw, list) and raw else raw
    except Exception as e:
        logger.debug("breakdown-dimension LLM pick failed, using fallback: %s", e)
        pick = None
    if isinstance(pick, dict):
        col = str(pick.get("column", "")).strip()
        if col in cand_names:
            return {"column": col, "rationale": str(pick.get("rationale", "")).strip()[:200]}
    fallback = candidates[0]
    return {"column": fallback["column"], "rationale": "Auto-selected: highest data coverage across both periods."}


def compute_priority_breakdowns(pri: dict, df: pd.DataFrame, values: dict, period: dict, dimension: dict) -> dict:
    """Per-member metric values for one dimension, reusing each computed metric's stored
    spec. Returns {dimension_column: {metric_name: [{member, current, prior, delta, unit,
    basis, status, verified}]}}."""
    dcol = str(dimension.get("column", "")) if isinstance(dimension, dict) else str(dimension or "")
    if not dcol or dcol not in df.columns:
        return {}
    members = dimension.get("members") if isinstance(dimension, dict) else None
    if not members:
        members = _dimension_members(df, dcol)
    out: dict = {}
    for mname, rec in (values or {}).items():
        if not isinstance(rec, dict) or rec.get("status") != STATUS_COMPUTED or rec.get("value") is None:
            continue
        spec = rec.get("spec")
        if not isinstance(spec, dict):
            continue
        cells = []
        for member in members:
            sub = df[df[dcol].astype(str) == str(member)]
            cell = _breakdown_cell(sub, period, spec, rec)
            cell["member"] = member
            cells.append(cell)
        out[mname] = cells
    if not out:
        return {}
    return {dcol: out}


def compute_priority_values(
    pri: dict, df: pd.DataFrame, schema_str: str, existing: dict | None = None, on_progress: Callable[..., None] | None = None
) -> dict:
    """Resolve every KPI + operational metric in `pri` to ONE scalar and persist the structure.

    Per metric group (a KPI and its operational metrics): one compact LLM spec call
    (not a giant script), then a deterministic template (`build_metric_script`) builds
    and runs the pandas code. A bad spec fails one metric, not the whole run.

    `existing` reuses already-recorded metric values (resume of a partial run); records
    with a final status are treated as done and never recomputed. `on_progress`, if given,
    is called after each group with the full result structure so the caller can persist
    incrementally (Ctrl+C keeps completed groups).
    """
    print("  Resolving time period...", flush=True)
    period = resolve_period(df, schema_str)
    print(f"  Period: {period['definition_text']}", flush=True)

    columns = set(str(c) for c in df.columns)
    all_metrics = list(_iter_priority_metrics(pri))
    metrics = [k for _, k in all_metrics if k.get("name")]
    measurements = {str(k.get("name", "")): k.get("measurement", "") for k in metrics}

    values: dict = {}
    for name, rec in (existing or {}).items():
        if isinstance(rec, dict) and rec.get("status") in (STATUS_COMPUTED, STATUS_NOT_COMPUTABLE, STATUS_ERROR):
            values[name] = dict(rec)

    reasons: dict = {}
    errored: set = set()

    prefiltered = {}
    for _, k in all_metrics:
        mname = str(k.get("name", ""))
        if not mname or mname in values:
            continue
        reason, missing_prim = _precheck_measurement(k.get("measurement", ""), period, df)
        if reason:
            values[mname] = _nc_record(period, k.get("measurement", ""), reason, missing_prim=missing_prim)
            prefiltered[mname] = reason

    eqs = pri.get("executive_questions") or []
    groups = []
    kpis = pri.get("kpis", [])
    if kpis:
        # New model: one group per KPI (the KPI + its operational metrics share the spec context).
        for k in kpis:
            group = [k] + [op for op in k.get("operational_metrics", []) if op.get("name")]
            if group:
                groups.append(group)
    elif eqs and isinstance(eqs[0], dict):
        for eq in eqs:
            group = [k for k in (eq.get("kpis", []) + eq.get("supporting_metrics", [])) if k.get("name")]
            if group:
                groups.append(group)
    if not groups and metrics:
        groups.append(metrics)

    print(f"  Metrics: {len(metrics)} across {len(groups)} group(s).", flush=True)
    if prefiltered:
        print(
            f"  Pre-filtered {len(prefiltered)} data-limited metric(s) (missing primitive): {', '.join(sorted(prefiltered))}",
            flush=True,
        )

    generated_at = datetime.now().isoformat(timespec="seconds")
    data_fp = data_fingerprint(df)

    def make_result() -> dict:
        return {
            "generated_at": generated_at,
            "data_fingerprint": data_fp,
            "engine_version": COMPUTE_ENGINE_VERSION,
            "period_definition": period["definition_text"],
            "period": {
                "date_column": period.get("date_column"),
                "current_start": period.get("current_start"),
                "current_end": period.get("current_end"),
                "prior_start": period.get("prior_start"),
                "prior_end": period.get("prior_end"),
            },
            "priorities": {
                pri.get("name", ""): {
                    "priority_ref": pri.get("name", ""),
                    "fingerprint": priority_fingerprint(pri),
                    "engine_version": COMPUTE_ENGINE_VERSION,
                    "values": values,
                }
            },
        }

    for gi, group in enumerate(groups, 1):
        group_names = [str(k.get("name")) for k in group]
        missing = [m for m in group_names if m not in values]
        if not missing:
            continue
        base_metrics_json = json.dumps(
            [{"name": k.get("name", ""), "metric": k.get("metric", ""), "measurement": k.get("measurement", "")} for k in group],
            ensure_ascii=False,
            indent=2,
        )
        base_prompt = prompts.render(
            "priority_spec_prompt.md",
            schema=schema_str,
            period_definition=period["definition_text"],
            metrics=base_metrics_json,
        )
        for attempt in range(1, 3):
            if not missing:
                break
            prompt = base_prompt
            if attempt > 1:
                err_lines = "\n".join(f"- {m}: {reasons.get(m, 'missing')}" for m in missing)
                prompt += (
                    "\n\nPREVIOUS ATTEMPT — these metrics FAILED or were MISSING:\n"
                    f"{err_lines}\n"
                    "Re-emit specs ONLY for the metrics above (exact names), following the schema."
                )
            print(f"  Group {gi}/{len(groups)} attempt {attempt}: generating specs for {len(missing)} metric(s)...", flush=True)
            raw = llm.ask_json(
                prompt,
                system_context="You are a data analyst. Return ONLY a JSON array of specs.",
                label=f"Generating specs (Group {gi})",
            )
            specs = _parse_specs(raw)
            returned_names = {str(s.get("name", "")) for s in specs}

            omitted = [m for m in missing if m not in returned_names]
            if omitted:
                if attempt == 1:
                    for m in omitted:
                        reasons[m] = "LLM could not express this measurement as a scalar spec (omitted)"
                    print(f"    {len(omitted)} metric(s) omitted this attempt; retrying in repair pass.", flush=True)
                else:
                    for m in omitted:
                        values[m] = _nc_record(
                            period,
                            measurements.get(m, ""),
                            "LLM could not express this measurement as a scalar spec (omitted)",
                        )
                        missing.remove(m)
                    print(f"    {len(omitted)} metric(s) inexpressible as scalar specs; marked not_computable.", flush=True)

            valid = []
            for spec in specs:
                mname = str(spec.get("name", ""))
                if mname not in missing:
                    continue
                ok, msg = _validate_spec(spec, columns, batch_names=set(missing))
                if not ok:
                    reasons[mname] = msg
                    continue
                valid.append(spec)
            if not valid:
                if missing and attempt == 1:
                    print(f"    No valid specs this attempt; repairing {len(missing)} metric(s)...", flush=True)
                    continue
                for m in missing:
                    values[m] = _nc_record(
                        period,
                        measurements.get(m, ""),
                        reasons.get(m, "no valid spec produced"),
                    )
                break
            code = build_metric_script(valid, period)
            print(f"    Running deterministic script ({len(valid)} metric(s))...", flush=True)
            ok, output = sandbox.execute_code(code, df)
            if not ok:
                print(f"    Script failed: {output[:300]}", flush=True)
                for m in missing:
                    reasons.setdefault(m, output[:500] or "script failed")
                    errored.add(m)
                continue
            parsed = _parse_compute_output(output)
            done_now = sum(1 for m in missing if m in parsed)
            print(f"    Parsed {done_now}/{len(missing)} metric(s) this attempt.", flush=True)
            spec_by_name = {str(s.get("name", "")): s for s in valid}
            for k in group:
                mname = str(k.get("name", ""))
                if mname not in missing or mname not in parsed:
                    continue
                rec = parsed[mname]
                is_custom = (spec_by_name.get(mname) or {}).get("kind") == "custom"
                source = "custom" if is_custom else None
                if isinstance(rec, dict) and rec.get("value") is None:
                    values[mname] = _nc_record(
                        period,
                        k.get("measurement", ""),
                        rec.get("null_reason") or "template returned null (e.g. empty prior period / division by zero)",
                        spec=dict(spec_by_name.get(mname) or {}),
                        basis=str(rec.get("basis", "")),
                        unit=str(rec.get("unit", "")),
                    )
                    if source:
                        values[mname]["source"] = source
                    missing.remove(mname)
                    reasons.pop(mname, None)
                elif (
                    isinstance(rec, dict) and isinstance(rec.get("value"), (int, float)) and not isinstance(rec.get("value"), bool)
                ):
                    values[mname] = _computed_record(
                        period,
                        k.get("measurement", ""),
                        rec["value"],
                        str(rec.get("unit", "")),
                        str(rec.get("basis", "")),
                        dict(spec_by_name.get(mname) or {}),
                    )
                    if source:
                        values[mname]["source"] = source
                    missing.remove(mname)
                    reasons.pop(mname, None)
                elif mname in parsed:
                    reasons[mname] = f"malformed value record: {rec}"
                    errored.add(mname)
            for m in list(missing):
                if m not in reasons:
                    reasons[m] = "metric omitted or not produced in output"
        if on_progress:
            on_progress(make_result())

    for _, k in all_metrics:
        mname = str(k.get("name", ""))
        if mname in values:
            continue
        reason = reasons.get(mname, "no value produced")
        values[mname] = _nc_record(period, k.get("measurement", ""), reason)
        if mname in errored:
            values[mname]["status"] = STATUS_ERROR

    computed = sum(1 for v in values.values() if v.get("status") == STATUS_COMPUTED)
    failed = len(values) - computed
    print(f"\n  Done: {computed} computed, {failed} not computable/errored.", flush=True)
    missing_prims = sorted(
        {
            str(v.get("missing_primitive"))
            for v in values.values()
            if v.get("status") == STATUS_NOT_COMPUTABLE and v.get("missing_primitive")
        }
    )
    if missing_prims:
        print(f"  New primitives suggested: {', '.join(missing_prims)}", flush=True)

    values, vsum = _verify_layers(values, df, period)
    print(_format_verify_summary(vsum), flush=True)
    return make_result()


def _close(a, b, rel=1e-6) -> bool:
    a, b = float(a), float(b)
    if a == 0 and b == 0:
        return True
    return abs(a - b) <= rel * max(abs(a), abs(b))


def _check_value(rec: dict) -> tuple[bool, str]:
    """Layer 0: deterministic plausibility rules keyed on spec agg/compare + unit.

    A null value is not a failure (already surfaced as not_computable); negative
    period-over-period deltas are legitimate and never flagged.
    """
    value = rec.get("value")
    if value is None:
        return True, "null value (status not computed)"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True, "non-numeric value skipped"
    if not math.isfinite(float(value)):
        return False, f"value {value} is not finite"
    spec = rec.get("spec") or {}
    agg = spec.get("agg")
    compare = spec.get("compare", "level")
    unit = str(rec.get("unit", "")).lower()
    if compare == "level":
        if agg in ("count", "count_distinct") and value < 0:
            return False, f"level count value {value} is negative"
        if unit == "currency" and value < 0:
            return False, f"level currency value {value} is negative"
        if agg in ("share", "topk_share") and not (0 <= value <= 1):
            return False, f"{agg} value {value} out of [0, 1]"
    return True, "ok"


def _aggregate(df: pd.DataFrame, mask, sub: dict):
    """Parent-process aggregate mirroring `_sel_block` in the sandbox template."""
    sel = df[mask]
    cond = sub.get("condition")
    if cond:
        if any(b in cond for b in _BLOCKED_IN_CONDITION):
            return None
        try:
            compile(cond, "<cond>", "eval")
        except SyntaxError:
            return None
        sel = df[(mask & eval(cond, {"df": df}))]
    agg = sub.get("agg")
    if agg == "count":
        return float(len(sel))
    if agg == "count_distinct":
        return float(sel[sub.get("value_column")].nunique())
    col = sub.get("value_column")
    if col is None or col not in df.columns:
        return None
    v = sel[col]
    if agg == "sum":
        return float(v.sum())
    if agg == "mean":
        return float(v.mean())
    if agg == "median":
        return float(v.median())
    if agg == "std":
        return float(v.std())
    return None


def _recomputable_spec(spec: dict) -> bool:
    if spec.get("kind") == "custom" or spec.get("steps") or spec.get("prep") or spec.get("input_ref"):
        return False
    return spec.get("agg") in ("count", "sum", "mean", "median", "std", "count_distinct", "ratio", "share")


def _period_masks(df: pd.DataFrame, period: dict) -> tuple:
    date_col = period.get("date_column")
    if date_col in df.columns:
        try:
            _dt = pd.to_datetime(df[date_col], errors="coerce")
        except Exception as e:
            logger.debug("period-mask date parse failed: %s", e)
            _dt = None
        if _dt is not None and period.get("current_start") and period.get("current_end"):
            cur = (_dt >= pd.Timestamp(period["current_start"])) & (_dt <= pd.Timestamp(period["current_end"]))
            pri = pd.Series(False, index=df.index)
            if period.get("prior_start") and period.get("prior_end"):
                pri = (_dt >= pd.Timestamp(period["prior_start"])) & (_dt <= pd.Timestamp(period["prior_end"]))
            return cur, pri
    return pd.Series(True, index=df.index), pd.Series(False, index=df.index)


def _recompute_value(df: pd.DataFrame, period: dict, spec: dict):
    """Layer 1: independently recompute a simple v1 spec in the parent process.

    Mirrors the deterministic template (masks + `_final_value`) so a mismatch with the
    recorded value is a genuine engine/spec regression, not a methodological difference.
    Returns None when the spec is not recomputable here or the value is null.
    """
    if not _recomputable_spec(spec):
        return None
    agg = spec.get("agg")
    compare = spec.get("compare", "level")
    cur_mask, pri_mask = _period_masks(df, period)

    if agg in ("count", "sum", "mean", "median", "std", "count_distinct"):
        sub = {"agg": agg, "value_column": spec.get("value_column"), "condition": spec.get("condition")}
        _c = _aggregate(df, cur_mask, sub)
        _p = _aggregate(df, pri_mask, sub) if compare != "level" else None
    else:
        vcol = spec.get("value_column")
        if agg == "share" and vcol is None:
            num = spec.get("numerator") or {"agg": "count", "condition": spec.get("condition")}
            den = spec.get("denominator") or {"agg": "count", "condition": None}
        else:
            num = spec.get("numerator") or {"agg": "sum", "value_column": vcol, "condition": spec.get("condition")}
            den = spec.get("denominator")
            if den is None and agg == "share":
                den = {"agg": "sum", "value_column": vcol, "condition": None}
        _cn = _aggregate(df, cur_mask, num)
        _cd = _aggregate(df, cur_mask, den)
        _c = (_cn / _cd) if (_cd is not None and _cd != 0) else None
        if compare != "level":
            _pn = _aggregate(df, pri_mask, num)
            _pd = _aggregate(df, pri_mask, den)
            _p = (_pn / _pd) if (_pd is not None and _pd != 0) else None

    return _apply_compare(compare, _c, _p)


def _verify_layers(values: dict, df: pd.DataFrame, period: dict) -> tuple[dict, dict]:
    """Run Layer 0 (plausibility) + Layer 1 (independent re-derivation) on computed records.

    Sets `verified` and a `verification` block with per-layer checks. Deterministic only —
    the LLM (Layer 2) runs on explicit request and can only unset `verified`.
    """
    updated = dict(values)
    summary = {
        "l0": {"pass": 0, "fail": 0},
        "l1": {"checked": 0, "match": 0, "mismatch": 0, "skipped": 0},
    }
    now = datetime.now().isoformat(timespec="seconds")
    for name, rec in updated.items():
        if not isinstance(rec, dict) or rec.get("status") != STATUS_COMPUTED or rec.get("value") is None:
            continue
        checks = list((rec.get("verification") or {}).get("checks") or [])
        l0_ok, l0_note = _check_value(rec)
        summary["l0"]["pass" if l0_ok else "fail"] += 1
        checks.append({"layer": "l0", "ok": l0_ok, "note": l0_note})

        spec = rec.get("spec") or {}
        if _recomputable_spec(spec):
            expected = _recompute_value(df, period, spec)
            actual = rec.get("value")
            summary["l1"]["checked"] += 1
            if expected is None and actual is None:
                l1_ok, l1_note = True, "both null"
            elif expected is None or actual is None:
                l1_ok = False
                summary["l1"]["mismatch"] += 1
                l1_note = f"null mismatch (re-derived {expected}, stored {actual})"
            elif _close(expected, actual):
                l1_ok, l1_note = True, f"re-derived {actual:.6g} within 1e-6"
            else:
                l1_ok = False
                summary["l1"]["mismatch"] += 1
                l1_note = f"re-derived {expected:.6g} != stored {actual:.6g}"
            if l1_ok and l1_note != "both null":
                summary["l1"]["match"] += 1
            checks.append({"layer": "l1", "ok": l1_ok, "note": l1_note})
        else:
            l1_ok = True
            summary["l1"]["skipped"] += 1
            checks.append({"layer": "l1", "ok": True, "note": "not re-derivable (composed spec)"})

        rec = dict(rec)
        rec["verified"] = bool(l0_ok and l1_ok)
        verification = dict(rec.get("verification") or {})
        verification["checks"] = checks
        verification["at"] = now
        rec["verification"] = verification
        updated[name] = rec
    return updated, summary


def _format_verify_summary(summary: dict) -> str:
    l0 = summary["l0"]
    l1 = summary["l1"]
    return (
        f"  Verification: L0 plausibility pass {l0['pass']}/fail {l0['fail']}; "
        f"L1 re-derivation match {l1['match']}/mismatch {l1['mismatch']}/skipped {l1['skipped']}."
    )


def _spec_columns(spec: dict) -> list[str]:
    cols = []
    for key in ("value_column", "group_by"):
        v = spec.get(key)
        if v:
            cols.append(v)
    for role in ("numerator", "denominator"):
        sub = spec.get(role) or {}
        if sub.get("value_column"):
            cols.append(sub["value_column"])
    for step in spec.get("steps") or []:
        for key in ("value", "group_by", "value_column"):
            v = step.get(key)
            if v:
                cols.append(v)
    for op in spec.get("prep") or []:
        for key in ("start", "end", "column"):
            v = op.get(key)
            if v:
                cols.append(v)
    return cols


def verify_priority_values(pri: dict, df: pd.DataFrame, values: dict, period: dict, schema_str: str) -> dict:
    """Layer 2: one LLM call asking whether each computed value matches the measurement
    and the sampled data. Flag-only — can only unset `verified` / annotate.
    """
    metrics = []
    touched = set()
    for name, rec in values.items():
        if not isinstance(rec, dict) or rec.get("status") != STATUS_COMPUTED or rec.get("value") is None:
            continue
        spec = rec.get("spec") or {}
        metrics.append(
            {
                "name": name,
                "measurement": rec.get("measurement", ""),
                "spec": spec,
                "value": rec.get("value"),
                "unit": rec.get("unit", ""),
                "compare": spec.get("compare", "level"),
            }
        )
        for c in _spec_columns(spec):
            if c in df.columns:
                touched.add(c)
    if not metrics:
        return values
    samples = {c: df[c].dropna().head(5).astype(str).tolist() for c in sorted(touched)}
    payload = json.dumps(
        {
            "period_definition": period.get("definition_text", ""),
            "samples": samples,
            "metrics": metrics,
        },
        ensure_ascii=False,
        indent=2,
    )
    prompt = prompts.render(
        "verify_priority_prompt.md",
        schema=schema_str,
        period_definition=period.get("definition_text", ""),
        metrics=payload,
    )
    raw = llm.ask_json(
        prompt, system_context="You are a data analyst. Return only valid JSON.", label="Verifying metric values (L2)"
    )
    if not isinstance(raw, dict):
        return values
    now = datetime.now().isoformat(timespec="seconds")
    updated = dict(values)
    for m in metrics:
        verdict = raw.get(m["name"])
        if not isinstance(verdict, dict):
            continue
        ok = verdict.get("ok")
        note = str(verdict.get("note", ""))[:300]
        rec = dict(updated.get(m["name"]) or {})
        verification = dict(rec.get("verification") or {})
        verification["llm_ok"] = bool(ok)
        verification["llm_note"] = note
        verification["at"] = now
        if ok is False:
            rec["verified"] = False
        rec["verification"] = verification
        updated[m["name"]] = rec
    return updated


def interpret_priority(pri: dict, values: dict, breakdowns: dict | None = None) -> str:
    """Quick tier: one LLM call narrating stored values (+ dimension breakdowns)."""
    prompt = prompts.render(
        "interpret_priority_prompt.md",
        priority_name=pri.get("name", ""),
        priority_description=pri.get("description", ""),
        values=json.dumps(values, ensure_ascii=False, indent=2),
        breakdowns=json.dumps(breakdowns or {}, ensure_ascii=False, indent=2),
    )
    return llm.ask(prompt, system_context="You are a business analyst.").strip()
