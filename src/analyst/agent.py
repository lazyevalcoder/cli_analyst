import json
import re
import time

from src.analyst import llm
from src.analyst import prompts
from src.analyst import sandbox
from src.analyst.config import CONFIG
from src.analyst.graph import KnowledgeGraph, format_diagnostic_kg, format_structural_kg


def _format_custom_instructions(instructions: list[str]) -> str:
    if not instructions:
        return ""
    lines = ["USER CUSTOM INSTRUCTIONS:"]
    for instr in instructions:
        lines.append(f"- {instr}")
    return "\n".join(lines)


def reason_and_plan(question: str, schema: str, structural_kg: dict, diagnostic_kg: dict, reasoning_framework: str, context: list[dict] = None, custom_instructions: list[str] = None, metric_brief: str = "") -> tuple:
    # Fast-path for follow-ups
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

    prompt = prompts.format(prompts.load("reasoning_prompt.md"),
        reasoning_framework=reasoning_framework,
        schema=schema,
        structural_kg=format_structural_kg(structural_kg) if isinstance(structural_kg, dict) else structural_kg,
        diagnostic_kg=format_diagnostic_kg(diagnostic_kg) if isinstance(diagnostic_kg, dict) else diagnostic_kg,
        question=question,
        context_section=context_section,
        custom_instructions=_format_custom_instructions(custom_instructions or []),
        metric_brief=metric_brief,
    )

    print("  [Phase 1] Reasoning about the question...", flush=True)
    response = llm.ask(prompt, system_context="You are an expert data analyst. Return only valid JSON.", temperature=0.1)

    data = llm.extract_json(response)
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


def agentic_answer(question: str, df, schema: str, structural_kg: dict, diagnostic_kg: dict, reasoning_framework: str, context: list[dict] = None, custom_instructions: list[str] = None, graph: KnowledgeGraph = None, metric_brief: str = "") -> str:
    reasoning, plan, strategy, persona = reason_and_plan(question, schema, structural_kg, diagnostic_kg, reasoning_framework, context=context, custom_instructions=custom_instructions, metric_brief=metric_brief)

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

    context_section = ""
    if context:
        lines = ["\nPREVIOUS ANALYSIS:"]
        for turn in context:
            lines.append(f"Q: {turn.get('question', '')}")
            lines.append(f"A: {turn.get('summary', '')}")
        context_section = "\n".join(lines)

    custom_instructions_str = _format_custom_instructions(custom_instructions or [])
    metric_brief_str = ""
    if metric_brief:
        precomputed = "PRE-COMPUTED VALUES" in metric_brief
        if precomputed:
            phase1 = (
                "PHASE 1 — METRICS: The brief includes PRE-COMPUTED VALUES for the KPIs and operational metrics. "
                "Interpret these values directly; do NOT recompute base metrics. Recompute (verify) a value once ONLY if it looks wrong. "
                "Metrics whose status is 'not_computable' or 'error' (or absent from the values) MAY be computed once yourself — mark them 'recomputed in-loop' in your output. "
                "If a metric genuinely cannot be computed from the data, do NOT substitute a different kind of value; state plainly why (in business language, not jargon) and move on."
            )
        else:
            phase1 = (
                "PHASE 1 — METRICS: Compute EVERY KPI in the brief (current value + delta vs prior period) using the exact Measurement formula and EXACT column names. Also compute its operational metrics (drivers). Use lookup_metric for any metric definition."
            )
        metric_brief_str = f"""

METRIC BRIEF — these are the pre-defined KPIs and operational metrics (drivers) for this priority:
{metric_brief}

TWO-PHASE EXECUTION:
{phase1}
PHASE 2 — DIMENSION DRILL-DOWN (only when it makes sense): For any KPI that is OFF (declining, below trend, anomalous, negative delta), slice it by its Drill-down dimensions to locate WHERE the issue originates (e.g., which product / agent / region / stage / account). Apply the appropriate analytical lens (decomposition, mix shift, variance). Healthy or stable KPIs skip the drill-down. Do NOT invent drill-down dimensions beyond those listed.
OUTPUT FORMAT (structured per-KPI insight):
  Q<n>: <question>
    KPI <name>: <value>, <delta vs prior> → <business read>
      Driver: <operational metric> explains <...>
      Implication: <...>
      [If KPI is off] By <dimension>: <where the issue originates> → <why>
"""
    system = f"""You are a data analyst investigating a question about data.

COLUMN NAMES AND TYPES:
{schema}

{custom_instructions_str}
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
If a step fails, analyze the error and try a corrected version.

METRIC CATALOG: Use lookup_metric to retrieve precise formulas for any KPI or metric mentioned in the question. Do NOT guess formulas — look them up.

KNOWLEDGE GRAPH: Use traverse_graph to explore relationships between metrics, dimensions, and business goals. This helps you understand what influences a metric, what it depends on, and how it connects to other business concepts.""" + metric_brief_str

    strategy_section = prompts.extract_strategy_section(strategy)
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

    _ns = sandbox._make_namespace(df)

    limit = CONFIG.max_iterations
    iteration = 0
    declined = False

    while iteration < limit:
        _step_start = time.time()
        total_elapsed = _step_start - _loop_start
        avg = total_elapsed / (iteration + 1)
        remaining = avg * (limit - iteration - 1)
        print(f"  [Step {iteration + 1}/{limit}] ({total_elapsed:.0f}s elapsed, ~{remaining:.0f}s remain) Thinking...", flush=True)

        state_summary = build_step_summary(analysis_state)
        if state_summary:
            messages[0]["content"] = system + "\n\n" + state_summary

        try:
            msg = llm.chat_with_tools(messages, tool_choice=_tool_choice, temperature=0.2)
        except Exception:
            if _tool_choice == "required":
                print("  Warning: tool_choice='required' not supported, falling back to 'auto'", flush=True)
                _tool_choice = "auto"
                msg = llm.chat_with_tools(messages, tool_choice=_tool_choice, temperature=0.2)
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

                    df_before = _ns["df"].copy(deep=True)

                    success, output = sandbox.execute_in_namespace(code, _ns)
                    step_dur = time.time() - _step_start
                    print(f"  [Step {iteration + 1}] {'OK' if success else 'ERROR'} ({step_dur:.1f}s): {output[:500]}")

                    analysis_state.append({"step": iteration + 1, "success": success, "output": output})

                    if success:
                        out_display = output
                        if len(out_display) > CONFIG.max_output_chars:
                            out_display = out_display[:CONFIG.max_output_chars] + f"\n... [output truncated to {CONFIG.max_output_chars} chars]"
                        result = f"Step {iteration + 1} completed successfully.\nOutput:\n{out_display}\n\nAll variables and df columns you created are available for future steps."
                    else:
                        _ns["df"] = df_before
                        result = f"Step {iteration + 1} FAILED with error:\n{output}\n\nThe DataFrame has been restored to its state before this failed step. Your code may have corrupted it. Try a different approach."

                elif fn_name == "final_answer":
                    print("\n  [Phase 4] Synthesizing final answer...")
                    return args.get("answer", "(no answer)")
                elif fn_name == "lookup_metric":
                    metric_name = args.get("name", "")
                    if graph:
                        entry = graph.get(metric_name)
                        if entry:
                            result = graph.format_for_prompt(metric_name)
                        else:
                            result = f"Metric '{metric_name}' not found in catalog."
                    else:
                        result = "Metric catalog not available."
                elif fn_name == "traverse_graph":
                    node_name = args.get("node", "")
                    relation = args.get("relation", None)
                    if graph:
                        result = graph.format_traverse(node_name, relation)
                    else:
                        result = "Knowledge graph not available."
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
                if iteration < limit - 1:
                    messages.append({"role": "user", "content": prompt})

        iteration += 1

        if iteration == limit and iteration >= CONFIG.max_iterations:
            last_summary = build_step_summary(analysis_state)
            print(f"\n  === Checkpoint: {iteration} steps completed ===")
            if last_summary:
                print(f"  {last_summary.replace(chr(10), chr(10) + '  ')[:400]}")
            try:
                ans = input(f"  Continue for {CONFIG.continuation_block} more steps? (y/N): ").strip().lower()
            except EOFError:
                ans = "n"
            if ans in ("y", "yes"):
                limit += CONFIG.continuation_block
                messages.append({
                    "role": "user",
                    "content": f"User approved {CONFIG.continuation_block} additional steps. You have {CONFIG.continuation_block} more steps of budget — keep investigating; do NOT wrap up yet.",
                })
            else:
                declined = True
                break

    reason = "you declined to continue" if declined else "the step budget was reached"
    print(f"\n  [Phase 4] Requesting final answer ({reason})...")
    state_summary = build_step_summary(analysis_state)
    messages.append({
        "role": "user",
        "content": f"""You have completed {limit} steps of analysis ({reason}).
You MUST now provide your final answer using the final_answer tool.

{state_summary}

Synthesize ALL findings above into a comprehensive answer.
If some steps failed, work with what succeeded.
Call final_answer NOW."""
    })

    for attempt in range(3):
        msg = llm.chat_with_tools(messages, temperature=0.4)
        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    continue
                if fn_name == "final_answer":
                    return args.get("answer", "(no answer)")
                if fn_name == "execute_code":
                    code = args.get("code", "")
                    success, output = sandbox.execute_in_namespace(code, _ns)
                    if len(output) > CONFIG.max_output_chars:
                        output = output[:CONFIG.max_output_chars] + f"\n... [output truncated to {CONFIG.max_output_chars} chars]"
                    result = f"Step (final synthesis): {'OK' if success else 'ERROR'}\n{output}"
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
        if attempt < 2:
            messages.append({"role": "user", "content": "Please provide your final answer using final_answer tool now."})

    successful_results = [e for e in analysis_state if e["success"]]
    if successful_results:
        summary = "\n\n".join(f"Step {e['step']}:\n{e['output']}" for e in successful_results)
        return f"Analysis completed with {len(successful_results)} successful steps:\n\n{summary}"
    return "(Analysis completed but could not generate final answer)"
