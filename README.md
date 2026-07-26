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
(analyst) priorities analyze 2            # Run full analysis on a priority
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
[Proactive] AI identifies strategic business priorities from KGs (priorities)
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
[Phase 3: EXECUTE] Run the plan (up to 10 iterations)
  - Each code block is self-contained (fresh namespace per call)
  - LLM receives explicit success/failure feedback
  - LLM can adapt plan based on findings
  - Tool calls forced via tool_choice="required"
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
    │   ├── custom_instructions.json    # User-defined analysis methodology
    │   └── briefing.json               # Cached strategic briefing
    └── analyses/
        ├── sales-decline/              # Auto-slugged from question
        │   └── turns.jsonl             # {"question": "...", "summary": "..."}
        └── _priority-profitability/    # Priority-linked analysis (prefixed with _)
            └── turns.jsonl
```

All projects live under a `projects/` folder. Everything is JSON — no database needed.

## Interactive Shell Commands

| Command | Description |
|---------|-------------|
| `status` | Show project state (data loaded? graphs built?) |
| `load <path>` | Load a CSV file, detect schema |
| `init` | Build KGs + reasoning framework + auto-identify priorities |
| `priorities` | Show strategic business priorities |
| `priorities regenerate` | Re-identify priorities from schema + KGs |
| `priorities analyze <n>` | Run full 4-phase analysis on a priority |
| `priorities show <n>` | Show saved analysis for a priority |
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
├── main.py                           # CLI entry point (interactive menu or init|open|list)
├── shell.py                          # Interactive shell (cmd.Cmd)
├── analyzer.py                       # Schema, KGs, reasoning framework, agentic loop
├── llm_client.py                     # OpenAI SDK wrapper (llama.cpp) + tool calling
├── sandbox.py                        # Safe Python execution (concurrent.futures, AST checks)
├── config.py                         # Centralized configuration (dataclass + env vars)
├── project.py                        # Project management (init, open, save, load)
├── storage.py                        # JSON persistence (save/load/append-jsonl)
├── knowledge/
│   ├── reasoning_framework.md        # Analysis strategies, personas, heuristics
│   ├── reasoning_prompt.md           # Phase 1 reasoning prompt template
│   ├── structural_kg_prompt.md       # Structural KG creation prompt
│   ├── diagnostic_kg_prompt.md       # Diagnostic KG creation prompt
│   ├── reasoning_context_prompt.md   # Dataset-specific context prompt
│   ├── priorities_prompt.md          # Strategic priority extraction prompt
│   └── briefing_prompt.md            # Per-priority strategic briefing prompt
├── requirements.txt                  # Dependencies
└── Idea.txt                          # Original project idea
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

All prompts are externalized to `knowledge/*.md` files and loaded at runtime.
This enables iteration on prompts without code changes.

| File | Used For |
|------|----------|
| `reasoning_prompt.md` | Phase 1: strategic reasoning + planning |
| `structural_kg_prompt.md` | Structural Knowledge Graph creation |
| `diagnostic_kg_prompt.md` | Diagnostic Knowledge Graph creation |
| `reasoning_context_prompt.md` | Dataset-specific reasoning context |
| `reasoning_framework.md` | Analysis strategies, personas, heuristics |
| `priorities_prompt.md` | Strategic business priority extraction |
| `briefing_prompt.md` | Per-priority strategic briefing generation |

### Strategy Extraction
After Phase 1 selects a strategy (e.g., "Diagnostic Analysis"), only that strategy's section is extracted from the framework and injected into Phase 3 — no redundant context.

## Reasoning Framework

The `knowledge/reasoning_framework.md` file provides:

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

**Commands:**
| Command | What it does |
|---------|-------------|
| `priorities` | List priorities with descriptions, key metrics, and analysis status |
| `priorities regenerate` | Re-run AI identification from schema + KGs |
| `priorities analyze <n>` | Run the full 4-phase pipeline on a priority — generates real findings with code execution, saves the result linked to that priority |
| `priorities show <n>` | Display saved analysis summary for a priority |

Priorities can be analyzed on-demand. Each priority analysis runs through the same 4-phase pipeline as a user question, auto-constructing a question from the priority's description and key metrics. Results are saved as analysis turns under `analyses/_priority-<name>/` and linked back to the priority.

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
| Context overflow | State summary truncated to last 2 steps, 200 chars each |
| One temperature fits all | 0.1 for JSON, 0.2 for code, 0.4 for synthesis |
| Malformed JSON crashes | `ask_json` retries 2x with sharper instruction |
| Tool args malformed | try/except with error feedback back to LLM |

## Setup

### Prerequisites
- Python 3.10+
- llama.cpp server running at `http://localhost:8080/v1`

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run
```bash
python main.py                        # Interactive menu
python main.py init my-project        # Create new project
python main.py open my-project        # Open existing project
python main.py list                   # List available projects
```

## Tool Calling

The LLM has access to two tools:

| Tool | Description |
|------|-------------|
| `execute_code(code)` | Run Python code on the DataFrame (available as `df`) |
| `final_answer(answer)` | Provide the final answer to the user |

### Adding More Tools

Edit `TOOLS` list in `llm_client.py`, then handle the tool in `analyzer.py`'s `agentic_answer()` function.

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

## Safety

Sandbox provides defense-in-depth:
- **Substring blocklist**: `import os`, `open(`, `exec(`, `eval(`, etc.
- **AST analysis**: Detects forbidden imports, dangerous attributes (`__class__`, `__builtins__`), dangerous calls (`exec`, `eval`, `compile`, `open`), pandas exec methods
- **Restricted builtins**: Allow-list of 30 safe builtins only
- **Denied attributes**: Python internals blocklist
- **Timeout**: 30-second hard limit via `concurrent.futures.ThreadPoolExecutor`
- **Isolated namespace**: Only `df`, `pd`, `json`, optionally `np`
- **Data protection**: DataFrame is deep-copied per call to prevent cross-step mutation

## Configuration

All settings centralized in `config.py` with environment variable overrides:

```python
CONFIG.base_url        # LLM endpoint (env: LLM_BASE_URL, default: http://localhost:8080/v1)
CONFIG.model           # Model name (env: LLM_MODEL, default: local)
CONFIG.max_iterations  # Max Phase 3 iterations (env: MAX_ITERATIONS, default: 10)
CONFIG.timeout_seconds # Code execution timeout (env: TIMEOUT_SECONDS, default: 30)
CONFIG.max_retries     # LLM retry count (env: MAX_RETRIES, default: 3)
CONFIG.retry_base_delay # Retry backoff base (env: RETRY_BASE_DELAY, default: 1.0)
CONFIG.temperature_json       # JSON generation (0.1)
CONFIG.temperature_code       # Code generation (0.2)
CONFIG.temperature_synthesis  # Final answer synthesis (0.4)
```

## What's New

- [x] **Strategic Priorities** — AI identifies key business priorities from KGs; run full analysis per priority
- [x] **Custom Analysis Instructions** — Persistent user-defined methodology rules injected into every analysis
- [x] **Strategic Briefing** — Per-priority strategic overview generated from schema + KGs

## Future Plans

- [ ] Add more tools (SQL queries, visualization, file export)
- [ ] Update KGs with computed insights
- [ ] Support multiple CSVs / joins
- [ ] Web UI
- [ ] Save/load analysis sessions

## Tech Stack

- **LLM**: llama.cpp (OpenAI-compatible API)
- **SDK**: openai (Python)
- **Data**: pandas, numpy
- **Execution**: Python exec() with safety constraints
- **Config**: Dataclass + environment variables
- **Persistence**: JSON files
