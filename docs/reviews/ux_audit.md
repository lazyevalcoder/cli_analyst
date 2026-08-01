# UX Audit — AI Data Analyst

Date: 2026-07-26
Audit scope: Full user journey from entry to exit

---

## Stall Detection & Progress (user waits with no feedback)

> **Progress note (2026-08):** Partially addressed since this audit. Phase 3 now prints a per-step line — `[Step N/M] (elapsed, ~ETA remain) Thinking...`, the executed code, and `OK/ERROR (duration)` with output — plus a checkpoint prompt at the free-step limit ("Continue for 5 more steps? (y/N)"). `priorities analyze` catches `KeyboardInterrupt` and saves progress gracefully. S2/S3 below remain open for general `analyze` (non-priority) runs.

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| S1 | **`init` blocks silently for 30-90s** — the LLM call has no spinner, no dots, no progress message. Just "Building structural KG (LLM call)..." followed by silence. User thinks the program froze. | P0 | `do_init`, `build_structural_kg`, `build_diagnostic_kg` |
| S2 | **`analyze` shows only `Thinking...` for 1-5+ minutes** — ~15 iterations each with 1-3 LLM calls. No ETA, no per-step timing, no "step 3/15" progress bar. User has no idea if it's 10% done or 90%. | P0 | `agentic_answer` loop (agent.py) |
| S3 | **No way to cancel** — once `analyze` starts, Ctrl+C dumps a raw traceback and collapses the shell. No graceful abort that preserves partial findings. | P0 | Shell entry point |
| S4 | **`follow` re-plans from scratch** — even "what about Region X?" does a full reasoning phase (30-60s delay). No fast-path for fact retrieval. | P1 | `reason_and_plan` |
| S5 | **`load` has a brief spinner ("Loading...")** — this is actually OK for the brief file I/O, but if the CSV were 10M rows it would stall silently too. | P2 | `do_load` |

## Guidance & Discoverability (user doesn't know what to do)

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| G1 | **Fresh project: no next-step hint** — `Analyses: 0` with zero guidance. User must guess to type `load` or `help`. | P0 | `_print_welcome` |
| G2 | **After `load`: tells user to `analyze` but that will fail** — KGs aren't built yet. Should say "Use `init` to build knowledge graphs." | P0 | `_print_welcome` |
| G3 | **Project list menu is just names** — `1. SalesOrders` — no data status, no KG status, no recency. User must open each one and run `status` to know anything. | P1 | `_list_projects` / `_interactive` |
| G4 | **`help` output is undifferentiated** — alphabetically sorted, no categories. New user can't tell setup commands (`load`, `init`) from query commands (`analyze`, `follow`) from review commands (`review`, `analyses`). | P1 | `help` (cmd.Cmd default) |
| G5 | **No way to re-show welcome hints** — once scrolled off, `help` is the only reference and it's alphabetical. | P1 | Missing `welcome` or `intro` command |
| G6 | **Slug shown only at end of analysis** — "Saved as 'why-did-sales-drop'". User can't know the slug in advance to note it down or reference it. | P2 | `do_analyze` |

## Error & Edge Case Handling

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| E1 | **Ctrl+C dumps raw traceback** — `KeyboardInterrupt` or `ConnectionError` from LLM server death shows Python internals, exits shell. | P0 | `agentic_answer`, shell loop |
| E2 | **LLM failure in `init` silently produces empty KGs** — "Warning: LLM returned invalid structural KG, using fallback" — no clear signal that init partially failed. User may think everything's fine. | P1 | `build_structural_kg`, `build_diagnostic_kg` |
| E3 | **`load` with existing data silently overwrites** — no warning that existing schema/KGs will be invalidated. KGs built for old data stay in place, now stale. | P1 | `do_load` |
| E4 | **`load data.xlsx` gives raw pandas error** — user shouldn't see `ValueError: Excel file format not supported` | P2 | `do_load` |
| E5 | **No graceful interruption** — if user quits (Ctrl+C or close terminal) during analysis, no partial results are saved. | P1 | Shell lifecycle |

## Missing Commands / Features

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| M1 | **No `delete` command** — can't remove a project or an analysis without manual filesystem surgery. | P1 | Missing |
| M2 | **No data preview** — `view schema` shows types but not actual row values. User must leave the shell to peek at data. | P2 | `do_view` |
| M3 | **No `check-llm` or `status llm`** — health check runs only at startup. If LLM server restarts mid-session, user can't verify. | P2 | `do_status` |
| M4 | **No project rename** — name is permanent after creation. | P2 | Missing |
| M5 | **No `export`** — no way to get analysis results out as text/markdown. | P2 | Missing |

## Information Density

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| I1 | **`analyses` lists slugs, not raw questions** — slug is a 60-char truncated, sanitized version. The first question text is shown but truncated to 80 chars. For long multi-turn analyses, you can't see the latest question. | P2 | `do_analyses` |
| I2 | **No timestamps anywhere** — projects, analyses, turns all lack timestamps. Can't tell when something was created or last modified. | P2 | All views |
| I3 | **`status` hides framework cache status** — user can't tell if reasoning framework is cached on disk or will need an LLM rebuild. | P2 | `do_status` |
| I4 | **`view` output is verbose with no grouping** — `view schema` on a 50-column dataset prints 50 lines. Could use type-based grouping. | P2 | `do_view` |
