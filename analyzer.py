import json
import re
import time
from pathlib import Path

import pandas as pd

from config import CONFIG
import llm_client
import sandbox

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


def _load_prompt(name: str) -> str:
    path = KNOWLEDGE_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _format_prompt(template: str, **kwargs: str) -> str:
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", value)
    return template


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
    prompt = _format_prompt(_load_prompt("structural_kg_prompt.md"), schema=schema)
    raw = llm_client.ask_json(prompt, system_context="You are a data architect. Return only valid JSON.")
    validated = _validate_structural_kg(raw)
    if not validated["nodes"] and not validated["edges"]:
        print("  ! LLM returned an empty or invalid structural KG. Expected nodes/edges describing the schema.")
        print("    Proceeding with an empty graph. `init` will continue but analysis quality will suffer.")
        return {"nodes": [], "edges": []}
    return validated


def build_diagnostic_kg(structural_kg: dict) -> dict:
    prompt = _format_prompt(_load_prompt("diagnostic_kg_prompt.md"), structural_kg=str(structural_kg))
    raw = llm_client.ask_json(prompt, system_context="You are a business analyst. Return only valid JSON.")
    validated = _validate_diagnostic_kg(raw)
    if not validated.get("chains") and not validated.get("hypotheses"):
        print("  ! LLM returned an empty or invalid diagnostic KG. Expected causal chains and hypotheses.")
        print("    Proceeding with an empty graph. `analyze` will have less guidance for root-cause analysis.")
        return {"chains": [], "dimensions_affecting": {}, "hypotheses": []}
    return validated


def format_structural_kg(kg: dict) -> str:
    lines = ["=== Structural Knowledge Graph ===", ""]
    for node in kg.get("nodes", []):
        lines.append(f"  [{node.get('type', '?').upper()}] {node.get('label', node.get('id', '?'))}")
    lines.append("")
    for edge in kg.get("edges", []):
        src = edge.get("source", "?")
        rel = edge.get("relation", "?")
        tgt = edge.get("target", "?")
        lines.append(f"  {src} --{rel}--> {tgt}")
    return "\n".join(lines)


def format_diagnostic_kg(kg: dict) -> str:
    lines = ["=== Diagnostic Knowledge Graph ===", ""]
    for chain in kg.get("chains", []):
        path_str = " -> ".join(chain.get("path", []))
        lines.append(f"  {chain.get('metric', '?')}: {path_str}")
        lines.append(f"    {chain.get('explanation', '')}")
        lines.append("")
    dims = kg.get("dimensions_affecting", {})
    if dims:
        lines.append("  Dimensions affecting metrics:")
        for metric, d_list in dims.items():
            lines.append(f"    {metric}: {', '.join(d_list)}")
    hyps = kg.get("hypotheses", [])
    if hyps:
        lines.append("")
        lines.append("  Diagnostic hypotheses:")
        for h in hyps:
            lines.append(f"    - {h}")
    return "\n".join(lines)


def build_llm_context(structural_kg: dict, diagnostic_kg: dict) -> str:
    return (
        "=== STRUCTURAL KNOWLEDGE GRAPH (what exists in the data) ===\n"
        f"{format_structural_kg(structural_kg)}\n\n"
        "=== DIAGNOSTIC KNOWLEDGE GRAPH (causal relationships) ===\n"
        f"{format_diagnostic_kg(diagnostic_kg)}\n"
    )


def load_reasoning_framework() -> str:
    """Load the reasoning framework from markdown file."""
    framework_path = KNOWLEDGE_DIR / "reasoning_framework.md"
    if framework_path.exists():
        return framework_path.read_text(encoding="utf-8")
    return ""


def build_reasoning_context(schema: str, structural_kg: dict, diagnostic_kg: dict) -> str:
    """Build dataset-specific reasoning context using LLM."""
    prompt = _format_prompt(_load_prompt("reasoning_context_prompt.md"),
        schema=schema,
        structural_kg=str(structural_kg),
        diagnostic_kg=str(diagnostic_kg),
    )
    return llm_client.ask_json(prompt, system_context="You are a data analyst. Return only valid JSON.")


def format_reasoning_context(context: dict) -> str:
    """Format the reasoning context for prompt inclusion."""
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


def extract_strategy_section(strategy_name: str) -> str:
    """Extract a single strategy section from the reasoning framework by name."""
    framework = load_reasoning_framework()
    if not framework or not strategy_name:
        return ""

    lines = framework.split("\n")
    out = []
    capturing = False
    found_header = False

    for line in lines:
        if line.startswith("### Strategy") and strategy_name.lower() in line.lower():
            capturing = True
            found_header = True
        elif capturing and line.startswith("### Strategy") and found_header:
            break
        if capturing:
            out.append(line)

    return "\n".join(out)


def get_full_reasoning_framework(schema: str, structural_kg: dict, diagnostic_kg: dict) -> str:
    """Get the complete reasoning framework: generic + dataset-specific."""
    generic_framework = load_reasoning_framework()
    reasoning_context = build_reasoning_context(schema, structural_kg, diagnostic_kg)
    context_text = format_reasoning_context(reasoning_context)
    return f"{generic_framework}\n\n{context_text}"


# =============================================================
#  Chain-of-Thought pipeline
# =============================================================

def reason_and_plan(question: str, schema: str, structural_kg: dict, diagnostic_kg: dict, reasoning_framework: str, context: list[dict] = None) -> tuple:
    # Fast-path for follow-ups: skip reasoning for simple drill-down questions
    if context:
        clean_question = re.sub(r"[^a-z0-9 ]", "", question.lower()).strip()
        fast_keywords = [
            "what about", "how about", "and what", "also what", "specifically",
            "tell me more", "elaborate", "go deeper", "dig into",
        ]
        is_drill_down = any(clean_question.startswith(kw) for kw in fast_keywords)
        is_short_simple = len(clean_question.split()) <= 8 and not clean_question.startswith("why")
        if is_drill_down or is_short_simple:
            last_turn = context[-1]
            reasoning = (
                f"Fast follow-up on: \"{last_turn.get('question', '')}\"\n"
                f"New question: {question}\n"
                "Proceeding directly to execution with prior context."
            )
            plan = [
                "Review previous analysis context for relevant findings",
                "Run code to answer the follow-up question",
                "Summarize new findings in context of prior analysis",
            ]
            print("  [Phase 1] Quick follow-up (skipping reasoning phase)...", flush=True)
            return reasoning, plan, "", ""

    context_section = ""
    if context:
        lines = ["", "PREVIOUS ANALYSIS CONTEXT (this is a follow-up question):"]
        for turn in context:
            lines.append(f"  Q: {turn.get('question', '')}")
            lines.append(f"  A: {turn.get('summary', '')}")
        lines.append("")
        lines.append("The above is the prior analysis. Plan the follow-up question below accordingly.")
        context_section = "\n".join(lines)

    prompt = _format_prompt(_load_prompt("reasoning_prompt.md"),
        reasoning_framework=reasoning_framework,
        schema=schema,
        structural_kg=format_structural_kg(structural_kg),
        diagnostic_kg=format_diagnostic_kg(diagnostic_kg),
        question=question,
        context_section=context_section,
    )

    print("  [Phase 1] Reasoning about the question...", flush=True)
    response = llm_client.ask(prompt, system_context="You are an expert data analyst. Return only valid JSON.", temperature=0.1)

    data = llm_client.extract_json(response)
    if data:
        strategy = data.get("strategy", "")
        persona = data.get("persona", "")
        reasoning = data.get("reasoning", response)
        plan = data.get("plan", [])
    else:
        strategy = ""
        persona = ""
        reasoning = response
        plan = []

    if not plan:
        plan = [
            "Check data overview: shape, columns, date range",
            "Analyze the main metric mentioned in the question",
            "Break down by relevant dimensions",
            "Summarize findings",
        ]

    return reasoning, plan, strategy, persona


def build_step_summary(analysis_state: list[dict]) -> str:
    if not analysis_state:
        return ""
    recent = analysis_state[-2:]
    lines = ["PREVIOUS RESULTS (last 2 steps):"]
    for entry in recent:
        step = entry["step"]
        success = entry["success"]
        output = entry["output"]
        status = "OK" if success else "FAILED"
        if len(output) > 200:
            output = output[:200] + "..."
        lines.append(f"  Step {step} [{status}]: {output}")
    return "\n".join(lines)


def agentic_answer(question: str, df, schema: str, structural_kg: dict, diagnostic_kg: dict, reasoning_framework: str, context: list[dict] = None) -> str:
    reasoning, plan, strategy, persona = reason_and_plan(question, schema, structural_kg, diagnostic_kg, reasoning_framework, context=context)

    print("\n  [Phase 1] Reasoning:")
    if strategy:
        print(f"    Strategy: {strategy}")
    if persona:
        print(f"    Persona: {persona}")
    print(f"    {reasoning[:300]}..." if len(reasoning) > 300 else f"    {reasoning}")
    print("\n  [Phase 2] Execution Plan:")
    for i, step in enumerate(plan, 1):
        print(f"    {i}. {step}")
    print()

    plan_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(plan))

    # ---- Build context section for follow-ups ----
    context_section = ""
    if context:
        lines = ["\nPREVIOUS ANALYSIS:"]
        for turn in context:
            lines.append(f"Q: {turn.get('question', '')}")
            lines.append(f"A: {turn.get('summary', '')}")
        context_section = "\n".join(lines)

    system = f"""You are a data analyst investigating a question about data.

COLUMN NAMES AND TYPES:
{schema}

CRITICAL RULES:
1. `df` is SHARED across ALL steps. Columns you add to `df` are available in future steps.
2. All variables you create also persist (e.g., `monthly_sales`, `q4_data`, `result`).
3. Use `df['NewCol'] = ...` to add derived columns — this mutates df in-place.
4. Do NOT reassign `df` (e.g., `df = df.groupby(...)`). The original `df` is the shared reference.
5. Use EXACT column names from COLUMN NAMES AND TYPES above.
6. You may deviate from the plan if findings warrant it.

STOPPING CRITERIA:
Call final_answer when ALL of these are met:
  a) You have answered the original question with specific numbers
  b) You have checked the basics (date range, null values)
  c) You have provided context (is the result meaningful?)
  d) You have acknowledged any limitations

APPROACH: Be exploratory but focused. Each code block should answer ONE question.
If a step fails, analyze the error and try a corrected version."""

    strategy_section = extract_strategy_section(strategy)
    strategy_guide = f"\n\nSTRATEGY GUIDE:\n{strategy_section}" if strategy_section else ""

    strategy_context = f"""ORIGINAL QUESTION: {question}

SELECTED STRATEGY: {strategy}
SELECTED PERSONA: {persona}

YOUR REASONING: {reasoning}

SUGGESTED PLAN (you may adapt based on findings):
{plan_text}{strategy_guide}{context_section}

Begin your analysis. Execute the first step of your plan."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": strategy_context},
    ]

    print("  [Phase 3] Executing plan...", flush=True)

    analysis_state = []
    _tool_choice = "required"
    _text_only_strikes = 0
    _loop_start = time.time()

    # Persistent namespace — df is shared across steps
    _ns = sandbox._make_namespace(df)

    for iteration in range(CONFIG.max_iterations):
        _step_start = time.time()
        total_elapsed = _step_start - _loop_start
        avg = total_elapsed / (iteration + 1)
        remaining = avg * (CONFIG.max_iterations - iteration - 1)
        print(f"  [Step {iteration + 1}/{CONFIG.max_iterations}] ({total_elapsed:.0f}s elapsed, ~{remaining:.0f}s remain) Thinking...", flush=True)

        state_summary = build_step_summary(analysis_state)
        if state_summary:
            messages[0]["content"] = system + "\n\n" + state_summary

        try:
            msg = llm_client.chat_with_tools(messages, tool_choice=_tool_choice, temperature=0.2)
        except Exception:
            if _tool_choice == "required":
                print("  Warning: tool_choice='required' not supported, falling back to 'auto'", flush=True)
                _tool_choice = "auto"
                msg = llm_client.chat_with_tools(messages, tool_choice=_tool_choice, temperature=0.2)
            else:
                raise

        if msg.tool_calls:
            _text_only_strikes = 0
            messages.append(msg)

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: invalid JSON in tool arguments: {tool_call.function.arguments[:200]}",
                    })
                    continue

                if fn_name == "execute_code":
                    code = args.get("code", "")
                    print(f"  [Step {iteration + 1}] Running code:")
                    print(f"    {code}")

                    # Snapshot df before execution
                    df_before = _ns["df"].copy(deep=True)

                    success, output = sandbox.execute_in_namespace(code, _ns)
                    step_dur = time.time() - _step_start
                    print(f"  [Step {iteration + 1}] {'OK' if success else 'ERROR'} ({step_dur:.1f}s): {output[:500]}")

                    analysis_state.append({"step": iteration + 1, "success": success, "output": output})

                    if success:
                        result = f"Step {iteration + 1} completed successfully.\nOutput:\n{output}\n\nAll variables and df columns you created are available for future steps."
                    else:
                        # Rollback df to pre-step state
                        _ns["df"] = df_before
                        result = f"Step {iteration + 1} FAILED with error:\n{output}\n\nThe DataFrame has been restored to its state before this failed step. Your code may have corrupted it. Try a different approach."

                elif fn_name == "final_answer":
                    print("\n  [Phase 4] Synthesizing final answer...")
                    return args.get("answer", "(no answer)")
                else:
                    result = f"Unknown tool: {fn_name}"

                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
        else:
            _text_only_strikes += 1
            if msg.content:
                print(f"  [Step {iteration + 1}] LLM message: {msg.content[:200]}")
                if _text_only_strikes >= 2:
                    prompt = "You MUST call execute_code or final_answer. Do NOT send text without a tool call."
                else:
                    prompt = "Continue. Use execute_code or final_answer."
                if iteration < CONFIG.max_iterations - 1:
                    messages.append({"role": "user", "content": prompt})

    # Force final answer
    print("\n  [Phase 4] Requesting final answer (max iterations reached)...")
    state_summary = build_step_summary(analysis_state)
    messages.append({
        "role": "user",
        "content": f"""You have completed {CONFIG.max_iterations} steps of analysis.
You MUST now provide your final answer using the final_answer tool.

{state_summary}

Synthesize ALL findings above into a comprehensive answer.
If some steps failed, work with what succeeded.
Call final_answer NOW."""
    })

    for attempt in range(3):
        msg = llm_client.chat_with_tools(messages, temperature=0.4)
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                if fn_name == "final_answer":
                    return args.get("answer", "(no answer)")
        if attempt < 2:
            messages.append({"role": "user", "content": "Please provide your final answer using final_answer tool now."})

    successful_results = [e for e in analysis_state if e["success"]]
    if successful_results:
        summary = "\n".join(f"Step {e['step']}: {e['output'][:200]}" for e in successful_results)
        return f"Analysis completed with {len(successful_results)} successful steps:\n\n{summary}"
    return "(Analysis completed but could not generate final answer)"
