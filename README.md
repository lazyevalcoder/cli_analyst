# AI Data Analyst

CLI-based AI data analyst with knowledge graphs and code interpreter. Like ChatGPT Code Interpreter, but local and graph-powered.

## Quick Start

```bash
# Interactive menu (create or open a project)
python main.py

# Or use CLI for direct commands:
python main.py init my-project     # Create a new project
python main.py open my-project     # Open an existing one
python main.py list                # List projects in current dir
```

Without arguments, you get an interactive prompt to create or open a project, then drop into the shell:

```
(analyst) load data/sales.csv
(analyst) init
(analyst) priorities regenerate           # AI identifies strategic priorities from KGs
(analyst) priorities compute 1             # Resolve every metric of priority 1 to one scalar, persist
(analyst) priorities interpret 1           # Quick one-call narration of stored values
(analyst) metrics                          # List all KPIs and supporting metrics
(analyst) metric show "Revenue Growth Trajectory"  # Full definition + formula
(analyst) priorities analyze 2            # Deep analysis (auto-computes values if stale, then seeded)
(analyst) analyze "Why did sales decline in Q4?"
(analyst) follow "What about the Northeast region specifically?"
(analyst) instructions add "Always compare QoQ and YoY for time-based questions"
(analyst) analyses
(analyst) quit
```

## How It Works

```
User creates project and loads CSV
       ↓
Schema extracted (columns, types, samples)
       ↓
`init` command: LLM builds Structural KG + Diagnostic KG + Reasoning Framework
       ↓
[Proactive] AI identifies strategic business priorities with executive questions and KPIs from KGs (priorities)
       ↓
[Proactive] Metric catalog built — each KPI and supporting metric has a precise formula
       ↓
[Proactive] Unified knowledge graph built — merges SKG nodes, DKG chains, and catalog into a traversable graph with typed relationships (INFLUENCES, DERIVED_FROM, SUPPORTS, etc.)
       ↓
[Proactive] AI generates a strategic briefing organized per priority (briefing)
       ↓
User asks question (analyze) or runs priority analysis (priorities analyze <n>)
       ↓
[Phase 1: REASON] LLM thinks using the reasoning framework
  - Selects analysis strategy (trend, comparison, diagnostic, etc.)
  - Considers persona (CFO, Sales Manager, etc.)
  - Decomposes into sub-questions
  - Respects user custom instructions
       ↓
[Phase 2: PLAN] LLM creates 3-5 step execution plan
       ↓
[Phase 3: EXECUTE] Run the plan (free steps, default 15, with user-approved continuation at checkpoints)
  - Each code block is self-contained (fresh namespace per call)
  - LLM receives explicit success/failure feedback
  - LLM can adapt plan based on findings
  - Tool calls forced via tool_choice="required"
  - Progress line per step: elapsed time, ETA, running code
  - Checkpoint at the free-step limit: "Continue for 5 more steps? (y/N)"
  - Tool-result stdout truncated at 3,000 chars for the LLM context (full output kept in state)
       ↓
[Phase 4: SYNTHESIZE] Final answer (saved as analysis turn)
       ↓
User can follow up with more questions (previous Q/Summary in context)
```

## Project Structure

```
projects/
└── my-project/
    ├── analyst.json                    # Project metadata
    ├── data/
    │   └── sales.csv                   # Copy of loaded dataset
    ├── graphs/
    │   ├── structural.json             # Structural Knowledge Graph
    │   └── diagnostic.json             # Diagnostic Knowledge Graph
    ├── metadata/
    │   ├── schema.json                 # Column info, types, samples
    │   ├── reasoning_framework.json    # Dataset-specific reasoning context
    │   ├── priorities.json             # Strategic business priorities
    │   ├── priority_values.json        # Computed scalar metric values (three-tier compute)
    │   ├── custom_instructions.json    # User-defined analysis methodology
    │   ├── metric_catalog.json         # Metric definitions (backward-compat)
    │   ├── knowledge_graph.json        # Unified graph: nodes + edges from KGs + catalog
    │   └── briefing.json               # Cached strategic briefing
    └── analyses/
        ├── sales-decline/              # Auto-slugged from question
        │   └── turns.jsonl             # {"question": "...", "summary": "..."}
        └── _priority-profitability/    # Priority-linked analysis (prefixed with _)
            └── turns.jsonl
```

All projects live under a `projects/` folder. Everything is JSON — no database needed.

### Priority Structure

Each priority in `priorities.json` follows this structure:

```json
{
  "name": "Build enough qualified pipeline",
  "description": "...",
  "executive_questions": [
    "Are we generating enough pipeline to sustain growth?",
    "Where is pipeline stalling?"
  ],
  "kpis": [
    {
      "name": "Active Pipeline Volume Growth",
      "metric": "deal_stage",
      "description": "...",
      "measurement": "Percentage change in the count of active opportunities vs the prior period",
      "operational_metrics": [
        { "name": "New Opportunity Inflow", "metric": "engage_date", "description": "...", "measurement": "..." }
      ],
      "analytical_lenses": ["Trends", "Cohorts"]
    }
  ]
}
```

Every KPI and operational metric must pass the **Metric Computability Rule Book**
(`src/analyst/prompts/metric_computability_rules.md`) — a hard five-test gate
(SCALAR, COMPUTABLE, BASELINE, ANCHOR, EXPRESSIBLE). A metric that fails any test is
not defined; the compute engine hard-fails anything that slips through, with a
plain-language reason — never a substituted or degraded value.

### Unified Knowledge Graph

After `init`, a unified `knowledge_graph.json` is built by merging the Structural KG, Diagnostic KG, and Metric Catalog into a single graph with typed nodes and relationships. This graph enables the LLM to traverse relationships during analysis — understanding what influences a metric, what it depends on, and how it connects to business goals.

## Interactive Shell Commands

| Command | Description |
|---------|-------------|
| `status` | Show project state (data loaded? graphs built?) |
| `load <path>` | Load a CSV file, detect schema |
| `init` | Build KGs + reasoning framework + auto-identify priorities |
| `priorities` | Show strategic business priorities with executive questions |
| `priorities regenerate` | Re-identify priorities (executive questions + KPIs + metrics) from schema + KGs; clears stored computed values |
| `priorities compute <n>` | Resolve every metric in priority n to ONE scalar value and persist to `metadata/priority_values.json` |
| `priorities analyze <n>` | Run full analysis on a priority — auto-computes values if missing/stale, then deep-seeded: interprets pre-computed KPIs + supporting metrics, drills into dimensions only for OFF KPIs |
| `priorities interpret <n>` | Quick one-LLM-call narration of stored values (value + unit, business read, OFF flags) |
| `priorities values <n>` | Print stored computed values (value, unit, period, verified, status) — audit aid |
| `priorities show <n>` | Show executive questions, KPIs, metrics, computed values, and saved analysis for a priority |
| `briefing [regenerate]` | Show strategic briefing organized per priority |
| `instructions` | List custom analysis instructions |
| `instructions add "..."` | Add a methodology rule (saved per project) |
| `instructions remove <n>` | Remove an instruction by number |
| `instructions clear` | Remove all custom instructions |
| `view schema` | List columns with types and samples (local) |
| `view entities` | List entity nodes from SKG (local) |
| `view metrics` | List measure nodes from SKG (local) |
| `view relationships` | Show edge relationships from SKG (local) |
| `view chains` | Show causal chains from DKG (local) |
| `view hypotheses` | Show diagnostic hypotheses (local) |
| `metrics [kpis\|supporting]` | List metric catalog (all, KPIs, or supporting metrics) |
| `metric show <name\|#>` | Full definition: formula, description, influences |
| `metric edit <name\|#> measurement "..."` | Override a metric's formula |
| `metric edit <name\|#> description "..."` | Override a metric's description |
| `metric reset <name\|#>` | Revert to LLM-generated version |
| `graph show` | Show node/edge type summary of the knowledge graph |
| `graph traverse <node> [relation]` | Explore graph connections (e.g., what INFLUENCES Revenue) |
| `analyze "question"` | Start a new analysis (4-phase pipeline) |
| `follow "question"` | Follow up in current analysis (Q/Summary history in context) |
| `analyses` | List all saved analyses |
| `review <slug>` | Show all Q/Summary turns in an analysis |
| `quit` | Save and exit |

### Follow-Up Context

When you use `follow`, the LLM sees only the **question/final-summary** pairs from previous turns — no raw code or intermediate thinking. This keeps context lean while preserving key findings:

```
PREVIOUS ANALYSIS:
Q: Why did sales decline in Q4?
A: Sales declined 15% in Q4 vs Q3. The Northeast region drove 60% of the drop...

Q: What about the Northeast region specifically?
A: Northeast sales fell 22% in Q4. The Furniture category declined 35%...
```

## Architecture

```
Jul25/
├── main.py                           # Thin entry point → src.analyst.__main__.main
├── serve_viewer.py                   # Standalone web viewer server
├── pyproject.toml                    # Packaging + dependencies (openai, pandas, numpy)
├── src/analyst/
│   ├── __main__.py                   # CLI entry point (interactive menu or init|open|list); `analyst` script
│   ├── shell.py                      # Interactive shell (cmd.Cmd)
│   ├── agent.py                      # Agentic 4-phase loop + KG formatters
│   ├── builder.py                    # Schema, KGs, reasoning framework, priorities, briefing
│   ├── llm.py                        # OpenAI SDK wrapper (llama.cpp) + tool calling
│   ├── graph.py                      # Unified graph: metric catalog + KG nodes/edges + traversal
│   ├── sandbox.py                    # Safe Python execution (subprocess, AST checks)
│   ├── config.py                     # Centralized configuration (dataclass + env vars)
│   ├── project.py                    # Project management (init, open, save, load)
│   ├── storage.py                    # JSON persistence (save/load/append-jsonl)
│   ├── prompts.py                    # Prompt loading + formatting helpers
│   ├── viewer.py                     # Embedded analysis viewer (HTTP server)
│   ├── viewer.html                   # Viewer frontend
│   └── prompts/
│       ├── reasoning_framework.md    # Analysis strategies, personas, heuristics
│       ├── reasoning_prompt.md       # Phase 1 reasoning prompt template
│       ├── structural_kg_prompt.md   # Structural KG creation prompt
│       ├── diagnostic_kg_prompt.md   # Diagnostic KG creation prompt
│       ├── reasoning_context_prompt.md  # Dataset-specific context prompt
│       ├── priorities_prompt.md      # Strategic priority extraction prompt
│       ├── metric_computability_rules.md  # Computability rule book (definition gate)
│       ├── priority_period_prompt.md # Current-vs-prior period resolution
│       ├── priority_spec_prompt.md   # Per-metric compute specs (compute tier)
│       ├── interpret_priority_prompt.md # Quick interpret tier narration
│       └── briefing_prompt.md        # Per-priority strategic briefing prompt
├── docs/                             # Concepts, reviews, design docs
└── scratch/                          # Scratch notes (incl. original idea)
```

## Chain-of-Thought Architecture

The system uses a 4-phase approach for intelligent data analysis:

### Phase 1: Reasoning
LLM thinks naturally about the question using the reasoning framework:
- Selects appropriate analysis strategy (trend, comparison, diagnostic, etc.)
- Considers relevant persona (CFO, Sales Manager, etc.)
- Decomposes into sub-questions
- Returns structured JSON with strategy, persona, reasoning, and plan

### Phase 2: Planning
LLM creates a focused 3-5 step execution plan with specific column names.
A 1-shot example guides the JSON output format.

### Phase 3: Execution
Each code block is **self-contained** — the sandbox resets between calls.
Tool use is forced (`tool_choice="required"`) with automatic fallback to `"auto"`.
After 2 consecutive text-only responses, a stronger enforcement message is sent.
LLM receives explicit feedback:
- `Step N completed successfully` (with sandbox independence reminder)
- `Step N FAILED with error: ... Please fix or skip`

LLM can **adapt the plan** based on findings.
Execution uses temperature 0.2 for reliable code generation.

**Stopping criteria** (LLM is instructed to call `final_answer` only when all are met):
1. Answered the original question with specific numbers
2. Checked the basics (date range, null values)
3. Provided context (is the result meaningful?)
4. Acknowledged any limitations

### Phase 4: Synthesis
LLM combines all findings into a comprehensive answer using temperature 0.4.

## Prompt Architecture

All prompts are externalized to `src/analyst/prompts/*.md` files and loaded at runtime.
This enables iteration on prompts without code changes.

| File | Used For |
|------|----------|
| `reasoning_prompt.md` | Phase 1: strategic reasoning + planning |
| `structural_kg_prompt.md` | Structural Knowledge Graph creation |
| `diagnostic_kg_prompt.md` | Diagnostic Knowledge Graph creation |
| `reasoning_context_prompt.md` | Dataset-specific reasoning context |
| `reasoning_framework.md` | Analysis strategies, personas, heuristics |
| `priorities_prompt.md` | Strategic business priority extraction |
| `priority_period_prompt.md` | Current-vs-prior period resolution (with machine-readable bounds) |
| `priority_spec_prompt.md` | Per-metric compute specs (three-tier compute tier) |
| `interpret_priority_prompt.md` | Quick one-call narration of stored values |
| `briefing_prompt.md` | Per-priority strategic briefing generation |

### Strategy Extraction
After Phase 1 selects a strategy (e.g., "Diagnostic Analysis"), only that strategy's section is extracted from the framework and injected into Phase 3 — no redundant context.

## Reasoning Framework

The `src/analyst/prompts/reasoning_framework.md` file provides:

### Analysis Strategies
- **Trend Analysis**: Time-based patterns, growth, decline
- **Comparison Analysis**: Dimensional breakdowns, ranking
- **Distribution Analysis**: Statistics, outliers, concentration
- **Composition Analysis**: Part-of-whole, contribution
- **Diagnostic Analysis**: Root cause, causal relationships
- **Ranking Analysis**: Top/bottom N, leaderboards

### Analysis Personas
- **CFO**: Profitability, ROI, cost control
- **Sales Manager**: Pipeline, conversion, territory
- **Marketing Analyst**: Campaign performance, segmentation
- **Operations Manager**: Efficiency, inventory, supply chain

### Universal Heuristics
- Always check date range first
- Understand the grain (what does each row represent?)
- Check for null values and duplicates
- Provide context when presenting results

### Dataset-Specific Context
At startup, the LLM generates:
- Dataset intent and purpose
- Key analysis focus areas
- Typical questions users would ask

## Strategic Priorities

After building KGs via `init`, the AI automatically identifies 3-5 key business priorities for the dataset (e.g., Revenue Growth, Profitability, Customer Segments). These are derived from the schema, entities, measures, and causal chains in the knowledge graphs.

Each priority follows a hierarchical structure:
- **Professional name** — consulting-grade naming (Revenue Growth Trajectory, Profit Margin Evolution)
- **Executive Questions** (2-5 per priority) — decision-focused questions that a business leader would ask (e.g., "Are we generating enough pipeline to sustain growth?", "Are we converting efficiently?")
  - **KPIs** (1-3 per question) — outcome measures, each with a precise business formula
  - **Supporting metrics** (3-7 per question) — driver metrics explaining KPI movement, each linked to the KPIs they influence

Priorities and their executive questions are MECE (Mutually Exclusive, Collectively Exhaustive) — no overlap between priorities or between questions within a priority.

**Commands:**
| Command | What it does |
|---------|-------------|
| `priorities` | List priorities with their executive questions, KPIs, supporting metrics, and analysis status |
| `priorities regenerate` | Re-run AI identification from schema + KGs; clears stored computed values |
| `priorities compute <n>` | Resolve every metric of priority n to ONE scalar value, persist to `metadata/priority_values.json` |
| `priorities analyze <n>` | Run the full deep pipeline — auto-computes values if missing/stale, then seeded: interprets pre-computed metrics, drills into dimensions only for OFF KPIs |
| `priorities interpret <n>` | Quick one-LLM-call narration of stored values |
| `priorities values <n>` | Print stored computed values (audit aid) |
| `priorities show <n>` | Display full detail — executive questions, KPIs (with formulas), supporting metrics, and any saved analysis |
| `metrics` | List all metric definitions in the project catalog |
| `metric show <name>` | View the full definition, including the LLM-lookupable formula |
| `metric edit <name> measurement "..."` | Override a formula (user corrections persist) |

### Metric Catalog

When the LLM needs a precise formula during analysis, it calls the `lookup_metric` tool on-demand rather than having every definition injected into the prompt. The catalog supports user overrides — edit a formula and the LLM will use your version going forward.

The metric catalog is built on a **knowledge graph** data model (`graph.py`): typed nodes (kpi, supporting_metric, entity, dimension, executive_question) and typed edges (INFLUENCES, DERIVED_FROM, SUPPORTS). The LLM can use the `traverse_graph` tool to explore these relationships, enabling root-cause analysis and impact analysis without the full graph in its context window.

Priorities can be analyzed on-demand. Each priority analysis is **metric-driven**: it computes every pre-defined KPI (with its exact measurement formula) plus supporting metrics, then drills down into dimensions only for KPIs that are OFF (declining, anomalous, negative delta). Drill-down dimensions come from the Diagnostic KG (`dimensions_affecting`), not invented by the LLM. Results are saved as analysis turns under `analyses/_priority-<name>/` and linked back to the priority.

After analysis, `priorities` shows a `✓ Analyzed` marker. Use `review <slug>` for the full turn history.

## Custom Analysis Instructions

Users can save persistent methodology rules that inject into every `analyze`/`follow` turn. This controls *how* the AI approaches questions.

**Example instructions:**
- *"For datasets with >12 months, always start with the most recent quarter and compare QoQ and YoY."*
- *"When analyzing profitability, always report gross margin and net margin separately."*
- *"If a question is ambiguous, ask clarifying questions before running code."*

**Commands:**
| Command | Description |
|---------|-------------|
| `instructions` | List all saved instructions |
| `instructions add "..."` | Add a new instruction |
| `instructions remove <n>` | Remove by number |
| `instructions clear` | Clear all instructions |

Instructions are saved per project in `metadata/custom_instructions.json` and injected into both Phase 1 (reasoning prompt) and Phase 3 (execution system prompt) of every analysis.

## LLM Reliability

Improvements for small models (7B-13B, 4K-8K context):

| Issue | Mitigation |
|-------|-----------|
| Free-text instead of tool calls | `tool_choice="required"` + 2-strike enforcement |
| JSON in markdown code blocks | Non-greedy regex that extracts ```json blocks first |
| No JSON example | 1-shot example in `reasoning_prompt.md` |
| Prompts waste context | KGs and framework stripped from Phase 3 system prompt |
| Independence rule ignored | Reminder injected after each successful execution |
| Context overflow | State summary truncated to last 2 steps, 200 chars each; tool-result stdout capped at `max_output_chars` (default 3000) |
| Runaway loops | Checkpoints: after `max_iterations` (default 15), user approves continuation in `continuation_block` (default 5) chunks |
| One temperature fits all | 0.1 for JSON, 0.2 for code, 0.4 for synthesis |
| Malformed JSON crashes | `ask_json` retries 2x with sharper instruction |
| Tool args malformed | try/except with error feedback back to LLM |
| Long blocking LLM calls look frozen | Heartbeat on every blocking call — elapsed-time tick every 10s (no streaming) |

## Setup

### Prerequisites
- Python 3.10+
- llama.cpp server running at `http://localhost:8080/v1`

### Install Dependencies
```bash
pip install -e .
```

### Run
```bash
python main.py                        # Interactive menu
python main.py init my-project        # Create new project
python main.py open my-project        # Open existing project
python main.py list                   # List available projects
```

## Tool Calling

The LLM has access to four tools:

| Tool | Description |
|------|-------------|
| `execute_code(code)` | Run Python code on the DataFrame (available as `df`) |
| `lookup_metric(name)` | Look up a metric's precise formula and description from the project catalog |
| `traverse_graph(node, [relation])` | Explore relationships in the knowledge graph (e.g., what INFLUENCES Revenue, what is DERIVED_FROM Orders) |
| `final_answer(answer)` | Provide the final answer to the user |

`lookup_metric` and `traverse_graph` are *information tools* — the LLM calls them to retrieve exact formulas or explore causal relationships without guessing. This keeps context lean since definitions are not pre-injected into every prompt.

### Adding More Tools

Edit `TOOLS` list in `llm.py`, then handle the tool in `agent.py`'s `agentic_answer()` function.

## Knowledge Graphs

### Structural KG
Created by LLM from CSV schema + sample data. Contains:
- Entities (Customer, Order, Product)
- Dimensions (Region, Category, Segment)
- Measures (Sales, Profit, Quantity)
- Relationships (HAS_ORDER, CONTAINS, ATTRIBUTE_OF, MEASURE_OF)

### Diagnostic KG
Created by LLM from Structural KG. Contains:
- Causal chains (sales depends on quantity, segment, etc.)
- Dimensions affecting each metric
- Diagnostic hypotheses ("if X declined, check Y")

### Unified Knowledge Graph
After `init`, the three sources are merged into a single `knowledge_graph.json` with typed nodes and edges. This graph powers the `traverse_graph` LLM tool, enabling the AI to reason about causal chains, data lineage (`DERIVED_FROM`), and business relationships during analysis without having the full graph in its prompt context.

## Safety

Sandbox provides defense-in-depth:
- **Substring blocklist**: `import os`, `open(`, `exec(`, `eval(`, etc.
- **AST analysis**: Detects forbidden imports, dangerous attributes (`__class__`, `__builtins__`), dangerous calls (`exec`, `eval`, `compile`, `open`), pandas exec methods
- **Restricted builtins**: Allow-list of 30 safe builtins only
- **Denied attributes**: Python internals blocklist
- **Timeout**: 30-second hard limit via `subprocess.run(timeout=...)` — process is killed on timeout
- **Isolated namespace**: Only `df`, `pd`, `json`, optionally `np`
- **Data protection**: DataFrame is deep-copied per call to prevent cross-step mutation

## Configuration

All settings centralized in `config.py` with environment variable overrides:

```python
CONFIG.base_url        # LLM endpoint (env: LLM_BASE_URL, default: http://localhost:8080/v1)
CONFIG.model           # Model name (env: LLM_MODEL, default: local)
CONFIG.max_iterations  # Free Phase 3 iterations before checkpointing (env: MAX_ITERATIONS, default: 15)
CONFIG.continuation_block # Extra steps granted per user approval at checkpoints (env: CONTINUATION_BLOCK, default: 5)
CONFIG.max_output_chars  # Tool-result stdout truncation cap for the LLM context (env: MAX_OUTPUT_CHARS, default: 3000)
CONFIG.timeout_seconds # Code execution timeout (env: TIMEOUT_SECONDS, default: 30)
CONFIG.max_retries     # LLM retry count (env: MAX_RETRIES, default: 3)
CONFIG.retry_base_delay # Retry backoff base (env: RETRY_BASE_DELAY, default: 1.0)
CONFIG.temperature_json       # JSON generation (0.1)
CONFIG.temperature_code       # Code generation (0.2)
CONFIG.temperature_synthesis  # Final answer synthesis (0.4)
```

## What's New

- [x] **Strategic Priorities** — AI identifies key business priorities from KGs; each priority has 2-5 executive questions, each with 1-3 KPIs and 3-7 supporting metrics; run full analysis per priority
- [x] **Executive Questions** — Decision-focused questions bridge priorities to KPIs (e.g., "Are we generating enough pipeline?"); priorities and their questions are MECE
- [x] **Metric Catalog** — Standalone per-project library of metric definitions; LLM looks up formulas on demand via `lookup_metric` tool
- [x] **Custom Analysis Instructions** — Persistent user-defined methodology rules injected into every analysis
- [x] **Strategic Briefing** — Per-priority strategic overview generated from schema + KGs
- [x] **Unified Knowledge Graph** — SKG, DKG, and metric catalog merged into a single traversable graph with typed relationships; LLM uses `traverse_graph` tool to explore causal chains, data lineage, and business connections on demand
- [x] **Metric-Driven Priority Analysis** — `priorities analyze <n>` computes pre-defined KPIs + supporting metrics via exact measurement formulas, then drills into DKG-sourced dimensions only for OFF KPIs; structured per-KPI insights (value, delta, driver, implication, by-dimension)
- [x] **Iteration Checkpoints** — after 15 free steps the agent asks whether to continue in blocks of 5, preventing runaway loops while keeping the LLM informed of its remaining budget
- [x] **Context-Size Guard** — tool-result stdout is truncated at 3,000 chars for the LLM context (full output kept in analysis state); Phase-4 synthesis routes `execute_code` results back to the LLM and falls back to full step outputs instead of a 200-char cut

## Future Plans

- [x] **Metric Computability Rule Book** — a hard five-test gate (SCALAR, COMPUTABLE, BASELINE, ANCHOR, EXPRESSIBLE) every KPI and operational metric must pass before it is proposed; injected into the priority and spec prompts. The compute engine hard-fails anything that slips through with a plain-language reason (`reason_display`) — a metric either computes or is honestly `Not computed`. No substituted values, no degraded versions.
- [x] **Three-tier priority analysis** (`compute` / `analyze` deep / `interpret` quick) — pre-compute scalar metric values into `metadata/priority_values.json`, seed the deep agentic loop with them, and add a single-call interpret tier. Compute uses a spec + deterministic template (the LLM emits per-metric specs, a fixed `build_metric_script` template runs them — no LLM-written pandas). See `docs/concepts/priority-compute-analyze-three-tier-split.md`.
- [x] **Closed compute-expressibility surface** — the spec DSL now covers every common scalar shape so a computable metric is never mis-rejected: FORM-1 `agg` over `prep`-derived columns (e.g. `mean(days between A and B)`), a `group` step with `group_by: null` (whole-frame scalar), a count-condition `share` (e.g. "share of orders using 'Express Air'"), and the `median` aggregate. A measurement→form routing table in `priority_spec_prompt.md` teaches the spec LLM the surface; omitted specs are retried once in the repair pass; `tests/test_spec_expressibility.py` locks every shape so a regression fails CI.
- [x] **Priority dimension breakdowns** — metrics in rows, dimension members in columns. `priorities compute <n>` asks the LLM for ONE schema-validated dimension per priority (SalesOrders: Region / Customer Segment / Ship Mode), then deterministically re-runs each computed metric's stored spec per member and persists a `{current, prior, delta}` matrix in `priority_values.json`. Per-member cells with no data or a zero baseline are honestly `not computed`. `priorities interpret <n>` reads the breakdown ("growth led by the East region, +111% vs +49% overall; West flat") and the viewer renders the matrix. `tests/test_priority_breakdowns.py` covers suggestion validation, per-member values, and persistence.
- [ ] **Scorecard artifact** — dashboard-matrix data model (outcomes × dimension cells) with filter-keyed values; the roadmap in `docs/concepts/roadmap.md`. Requires the priorities-quality foundation (validator + blueprint + few-shot bank) first.
- [ ] Update KGs with computed insights
- [ ] Support multiple CSVs / joins
- [ ] Web UI
- [ ] **Config-as-code** — declarative project file (YAML/JSON) where developers define priorities, KPIs, metrics, and methodology; analysts just analyze

## Tech Stack

- **LLM**: llama.cpp (OpenAI-compatible API)
- **SDK**: openai (Python)
- **Data**: pandas, numpy
- **Execution**: Python exec() with safety constraints
- **Config**: Dataclass + environment variables
- **Persistence**: JSON files
