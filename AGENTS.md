# AGENTS.md

Guidance for AI agents working in this repo.

## task_master.md — living task board

`task_master.md` at the repo root is a Trello-style board kept in markdown:
one line per task, columns as `##` sections (Ideas → Planned → Ready →
Active → Done / Parked). It is a living artifact, not a snapshot.

- **During work:** when the human captures an idea mid-session, add a line
  under `## 🌱 Ideas` (see the format/rules in the file — one line, `T-###`
  ID, tags).
- **At the end of a session** that touched product or code-quality work,
  reconcile the board:
  - move items that shipped into `## 🏁 Done` and flip `[ ]` → `[x]`;
  - move discussed-but-unbuilt ideas to `Ready`/`Planned` as appropriate,
    or leave in `Ideas`;
  - add newly-decided tasks; don't silently drop anything discussed.
- Tagging: use `cost=cheap|medium|expensive` (the "API cheap" gate) and
  `doc=concepts/<file>.md` once a design note exists.
- Never break the one-line-per-task rule; keep titles short.

## Project conventions

- Prompt text lives in `src/analyst/prompts/*.md`, loaded at runtime.
- No code comments unless asked. Follow existing style in neighboring files.
- Tests live in `tests/` (pytest). Design/status notes live in
  `docs/concepts/`.