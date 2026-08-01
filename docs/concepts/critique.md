# Codebase Critique

## 1. The Sandbox Is Not a Sandbox (Critical, Quick Win) — ✅ Resolved

**File:** `src/analyst/sandbox.py`

The sandbox used to run LLM-generated Python code **in the same process** as the application.

- The `BLOCKED_SUBSTRINGS` blocklist (line 13-18) is trivially bypassable via string concatenation (`"import" + " os"`), `getattr` chains, or whitespace variants like `import\xa0os`.
- `ThreadPoolExecutor` with `future.result(timeout=...)` cannot kill a thread. An `while True: pass` loop from the LLM will:
  - Hang the process indefinitely
  - Leak threads (multiple analyses accumulate stuck threads)
  - There is no mechanism to detect or clean up hung threads.

**Fix:** Use `subprocess.run()` with a hard process kill via `subprocess.TimeoutExpired`. This provides true isolation and enforceable timeouts.

**Status:** Fixed. `execute_code` / `execute_in_namespace` now serialize the namespace to a temp file and run the code in a separate process via `sandbox_worker.py`, which re-validates AST checks, execs with restricted builtins, and round-trips state back through pickle. `subprocess.run(timeout=CONFIG.timeout_seconds)` hard-kills the child on timeout (verified with an infinite loop). Cross-step variable/df state still persists.

## 2. God Object Shell (High) — Partially Resolved

**File:** `src/analyst/shell.py`

`AnalystShell` is 1,284 lines. `do_priorities` alone is 277 lines handling 4 subcommands in one method.

Remaining duplication:
- Priorities regeneration logic duplicated in `do_init` (line 380-398) and `do_priorities regenerate` (line 505-523).

**Fix:** Extract command handlers into separate modules. ~~Move shared formatters into `graph.py` (Quick Win — eliminates 44 lines of copy-paste). Deduplicate slug generation.~~

**Status:** Formatters and slugs deduplicated. `format_structural_kg` / `format_diagnostic_kg` now live in `graph.py` and are imported by both `agent.py` and `builder.py`. `_slugify` in `graph.py` accepts a `sep` param, and `shell.py`'s `_make_slug` delegates to it (`sep="-"`). The `do_init` / `do_priorities regenerate` duplication and command-handler extraction remain.

## 3. Zero Tests (High)

No `tests/` directory. No unit tests, integration tests, or end-to-end tests.

Barriers to testing:
- Direct import coupling: `agent.py` imports `llm`, `sandbox`, `prompts`, `config` directly with no interfaces.
- Global singleton `CONFIG = Config()` makes it impossible to run tests with different configurations.
- `datetime.now()` inline calls (project.py:58, shell.py:591,1038,1115) make time-dependent tests non-deterministic.

**Fix:** Start with tests for `KnowledgeGraph` (Quick Win — well-structured and testable; a good starting point for test infrastructure). Add dependency injection or factory functions for LLM and sandbox.

## 4. Overly Broad Error Handling (High)

| Location | Issue |
|---|---|
| `llm.py:94` | `_retry` catches `except Exception` — programming bugs inside the function silently retry and re-raise with misleading final error |
| `shell.py:69-71` | `onecmd` wraps all commands in `except Exception` broadcast, losing stack traces |
| `storage.py:16` | `load_json` catches `OSError` and returns default — silently lossy on corrupted files |
| `storage.py:31-32` | `read_jsonl` catches `json.JSONDecodeError` and returns `[]`, losing all data from a partially-corrupt file |
| `agent.py:237-243` | `chat_with_tools` fallback silently catches the exception when `tool_choice="required"` fails |

**Fix:** Catch specific exceptions. Log warnings for recoverable errors. Re-raise unexpected exceptions.

## 5. Non-Atomic Project Saves (High)

**File:** `src/analyst/project.py:57-77`

`save()` writes 8 files sequentially with no transaction. A crash midway leaves the project corrupted:
- Some metadata files updated, others stale
- No recovery mechanism
- No backup before writes

**Fix:** Write to temp files, then atomically rename. Or use a write-ahead log.

## 6. No Logging Framework (Medium, Quick Win)

All output uses `print()`. No log levels, no file logging, no way to silence verbose output for automated/non-interactive use.

**Fix:** Replace `print()` with `logging` module (one afternoon of work, permanent improvement). Add `-v`/`--quiet` flags to control verbosity.

## 7. Briefing Prompt Bug (Medium, Quick Win)

**File:** `src/analyst/prompts/briefing_prompt.md`

Uses `{{` / `}}` literal braces, but `prompts.format()` uses `str.replace()` not `str.format()`. The LLM receives literal double-braces and is instructed to produce JSON containing them — the instructions themselves are malformed.

**Fix:** Use `{` / `}` directly. If escaping is needed, implement it in `prompts.format()`.

## 8. Arbitrary File Loading (Medium)

**File:** `src/analyst/shell.py:264`

`do_load` accepts any user-supplied path without restriction. An attacker could load `/etc/passwd`, `~/.ssh/id_rsa`, or project-internal metadata files.

**Fix:** Validate that the resolved path is within the expected data directory. Reject system paths.

## 9. Brittle JSON Fallback (Medium)

**File:** `src/analyst/agent.py:75-87`

When the LLM's JSON response fails to parse, the fallback assigns the entire raw text to `reasoning` and uses hardcoded default steps. The parsing error is silently discarded — the user never knows the LLM produced bad output.

**Fix:** Log the parsing failure. Retry with stricter formatting instructions before falling back.

## 10. No LLM Provider Abstraction (Medium)

**File:** `src/analyst/llm.py`

Hard-coupled to OpenAI-compatible API. No support for:
- API key authentication
- Streaming responses
- Structured output / JSON mode
- Multiple model fallback
- Non-OpenAI providers (Anthropic, HuggingFace)

The SDK version compatibility is unchecked — `openai` 0.x vs 1.x have breaking API changes.

**Fix:** Abstract behind a `LLMProvider` interface. Add version check at startup.

## 11. Analysis Is a Single Monolithic Pass (Medium) — Partially Addressed

**File:** `src/analyst/agent.py`, `src/analyst/shell.py`

`priorities analyze <n>` does everything in one agentic loop: derive base metrics, drill down, narrate. Observed failure modes during real use on Pipeline Analytics:

- A run exhausted its 10-step budget on exploration, `final_answer` never fired, Phase-4 forced synthesis **dropped `execute_code` results** (they weren't routed back to the LLM), and the fallback truncated each step to 200 chars — the stored `analysis_summary` was a raw step dump ("Analysis completed with 9 successful steps"), unusable for auditing.
- Every run re-pays the base-metric computation cost; there is no persistent numeric artifact ("what is Product Portfolio Concentration right now?" is unanswerable without re-running analysis).

**Status:** Phase-4 now routes `execute_code` results back to the LLM; the fallback emits full step outputs (no 200-char cut); tool-result stdout is capped at `CONFIG.max_output_chars` (3000) for the LLM context only. Runaway loops are bounded by user-approved checkpoints (`max_iterations` 15, `continuation_block` 5).

**Fix (proposed):** Three-tier split — `priorities compute <n>` (persist scalar metric values), `priorities analyze <n>` deep (seeded by stored values), `priorities interpret <n>` (single-call narration). Design note: `docs/concepts/priority-compute-analyze-three-tier-split.md`.

## 12. Free-Text Measurements Are the Quality Ceiling (High) — Decided, Not Started

**File:** `src/analyst/prompts/priorities_prompt.md`, `metadata/priorities.json`, `metadata/metric_catalog.json`

`measurement` is free-text business language ("(Current period Count − Prior period Count) ÷ Prior period Count, computed quarterly with year-over-year comparison"). Everything downstream (analysis, briefing, future scorecard) depends on the LLM translating it correctly. Audits of Pipeline Analytics output found:

- ACT stage never emitted (all priorities stopped at WHERE)
- Duplicated metrics (same measure × lens repeated); naming violations (lens/dimension words in names)
- Computability failures (references columns not in schema); question→KPI alignment drift
- Non-scalar formulas (one value *per agent/stage/product* instead of one number)

Root cause: the model copies the prompt's hard-coded EXAMPLE structure instead of following the rules. Patching per dataset is a losing game.

**Fix (decision):** O2 deterministic validator + O3 blueprint pass + curated few-shot bank (retrieved by schema shape, gated by the validator). Full plan in `docs/concepts/roadmap.md` ("Priorities Generation Quality"). Note: the validator also gives numeric checks (Win Rate ∈ [0,1], plausible deltas) once `priorities compute` exists.

## 13. No Persistent Computed Values (Medium) — Proposed

**File:** `src/analyst/project.py`, `metadata/`

`metric_catalog.json` stores *definitions*, never *values*. Nothing persists "Opportunity Volume Growth = +17% QoQ" as data. The roadmap's scorecard requires a filter-keyed value matrix; the three-tier split introduces `metadata/priority_values.json` with `value`/`status`/`fingerprint` per metric — deliberately shaped to be scorecard-compatible (`{filters, value}` cells).

**Fix:** Add `priority_values` to `Project` persistence, auto-invalidate on `priorities regenerate`. See `docs/concepts/priority-compute-analyze-three-tier-split.md`.
