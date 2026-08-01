import pandas as pd

from src.analyst import llm
from src.analyst import prompts
from src.analyst.graph import format_diagnostic_kg, format_structural_kg


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
    prompt = prompts.format(prompts.load("structural_kg_prompt.md"), schema=schema)
    raw = llm.ask_json(prompt, system_context="You are a data architect. Return only valid JSON.")
    validated = _validate_structural_kg(raw)
    if not validated["nodes"] and not validated["edges"]:
        print("  ! LLM returned an empty or invalid structural KG. Expected nodes/edges describing the schema.")
        print("    Proceeding with an empty graph. `init` will continue but analysis quality will suffer.")
        return {"nodes": [], "edges": []}
    return validated


def build_diagnostic_kg(structural_kg: dict) -> dict:
    prompt = prompts.format(prompts.load("diagnostic_kg_prompt.md"), structural_kg=str(structural_kg))
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


def build_reasoning_context(schema: str, structural_kg: dict, diagnostic_kg: dict) -> str:
    prompt = prompts.format(prompts.load("reasoning_context_prompt.md"),
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


def identify_priorities(schema: str, structural_kg: dict, diagnostic_kg: dict) -> list:
    prompt = prompts.format(
        prompts.load("priorities_prompt.md"),
        schema=schema,
        structural_kg=str(structural_kg),
        diagnostic_kg=str(diagnostic_kg),
    )
    raw = llm.ask_json(prompt, system_context="You are a strategy consultant. Return only valid JSON.")
    priorities = raw.get("priorities", []) if isinstance(raw, dict) else []
    if not priorities:
        return []
    return priorities


def format_priority_metric_brief(pri: dict, diagnostic_kg: dict = None) -> str:
    """Render a priority's KPIs + supporting metrics (with DKG drill-down dimensions) as a prompt brief."""
    from src.analyst.graph import _slugify
    eqs = pri.get("executive_questions", [])
    if not eqs:
        return ""
    dims = diagnostic_kg.get("dimensions_affecting", {}) if isinstance(diagnostic_kg, dict) else {}
    dims_lower = {str(k).lower(): v for k, v in dims.items()}

    def drill_dims(metric_name: str, source_col: str) -> list:
        for key in (str(metric_name).lower(), _slugify(metric_name), str(source_col).lower(), _slugify(source_col)):
            if key in dims_lower:
                return dims_lower[key]
        return []

    lines = [f"PRIORITY: {pri.get('name', '')}", ""]
    for i, eq in enumerate(eqs, 1):
        lines.append(f"EXECUTIVE QUESTION {i}: {eq.get('question', '?')}")
        for k in eq.get("kpis", []):
            col = k.get("metric", "")
            lines.append(f"  KPI: {k.get('name', '?')} (source: {col})")
            if k.get("measurement"):
                lines.append(f"    Measurement: {k.get('measurement', '')}")
            dd = drill_dims(k.get("name", ""), col)
            if dd:
                lines.append(f"    Drill-down dimensions (from DKG): {', '.join(dd)}")
        for s in eq.get("supporting_metrics", []):
            col = s.get("metric", "")
            inf = s.get("influences", [])
            inf_str = f" [influences: {', '.join(inf)}]" if inf else ""
            lines.append(f"  SUPPORTING: {s.get('name', '?')} (source: {col}){inf_str}")
            if s.get("measurement"):
                lines.append(f"    Measurement: {s.get('measurement', '')}")
        lines.append("")
    return "\n".join(lines).rstrip()


def generate_briefing(schema: str, structural_kg: dict, diagnostic_kg: dict, priorities: list) -> dict:
    prompt = prompts.format(
        prompts.load("briefing_prompt.md"),
        schema=schema,
        structural_kg=str(structural_kg),
        diagnostic_kg=str(diagnostic_kg),
        priorities=str(priorities),
    )
    raw = llm.ask_json(prompt, system_context="You are a strategy consultant. Return only valid JSON.")
    if not isinstance(raw, dict):
        return {"priority_insights": [], "suggested_questions": []}
    return raw
