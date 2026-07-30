# Codebase Critique

## 1. The Sandbox Is Not a Sandbox (Critical)

**File:** `src/analyst/sandbox.py`

The sandbox runs LLM-generated Python code **in the same process** as the application.

- The `BLOCKED_SUBSTRINGS` blocklist (line 13-18) is trivially bypassable via string concatenation (`"import" + " os"`), `getattr` chains, or whitespace variants like `import\xa0os`.
- `ThreadPoolExecutor` with `future.result(timeout=...)` cannot kill a thread. An `while True: pass` loop from the LLM will:
  - Hang the process indefinitely
  - Leak threads (multiple analyses accumulate stuck threads)
  - There is no mechanism to detect or clean up hung threads.

**Fix:** Use `subprocess.run()` with a hard process kill via `subprocess.TimeoutExpired`. This provides true isolation and enforceable timeouts.

## 2. God Object Shell (High)

**File:** `src/analyst/shell.py`

`AnalystShell` is 1,284 lines. `do_priorities` alone is 277 lines handling 4 subcommands in one method.

Duplicated code:
- `format_structural_kg` / `format_diagnostic_kg` are copy-pasted verbatim between `agent.py:92-123` and `builder.py:105-136`.
- `_make_slug` (shell.py:20-22) and `_slugify` (graph.py:9-10) implement the same logic with different delimiters.
- Priorities regeneration logic duplicated in `do_init` (line 380-398) and `do_priorities regenerate` (line 505-523).

**Fix:** Extract command handlers into separate modules. Move shared formatters into `graph.py`. Deduplicate slug generation.

## 3. Zero Tests (High)

No `tests/` directory. No unit tests, integration tests, or end-to-end tests.

Barriers to testing:
- Direct import coupling: `agent.py` imports `llm`, `sandbox`, `prompts`, `config` directly with no interfaces.
- Global singleton `CONFIG = Config()` makes it impossible to run tests with different configurations.
- `datetime.now()` inline calls (project.py:58, shell.py:591,1038,1115) make time-dependent tests non-deterministic.

**Fix:** Start with tests for `KnowledgeGraph` (most self-contained). Add dependency injection or factory functions for LLM and sandbox.

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

## 6. No Logging Framework (Medium)

All output uses `print()`. No log levels, no file logging, no way to silence verbose output for automated/non-interactive use.

**Fix:** Replace `print()` with `logging` module. Add `-v`/`--quiet` flags to control verbosity.

## 7. Briefing Prompt Bug (Medium)

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

---

## Quick Wins (Low Effort, High Impact)

1. **Move duplicated formatters** into `graph.py` — eliminates 44 lines of copy-paste between `agent.py` and `builder.py`.
2. **Add `subprocess` sandbox** — replaces the current in-process sandbox with real isolation.
3. **Add `logging` module** — swap `print()` for `logging.info()`. One afternoon of work, permanent improvement.
4. **Fix briefing prompt syntax** — change `{{` to `{` in `briefing_prompt.md`.
5. **Add `KnowledgeGraph` unit tests** — the class is well-structured and testable; a good starting point for test infrastructure.
