# Task Master

Lightweight Trello-style board as a single markdown file. One line per task.
Columns are `##` sections; status change = move the line between sections.

Lifecycle: `🌱 Ideas` → `📋 Planned` → `✅ Ready` → `🔨 Active` → `🏁 Done` / `⏸️ Parked`

- **Ideas** — raw brainstorm capture. Cheap to write down, unproven. No doc yet.
- **Planned** — a concept exists in `docs/concepts/*.md`; design agreed. Link it with `doc=`.
- **Ready** — gated on "time + API cheap"; pick from here when you have a budget.
- **Active** — being worked on right now.
- **Done** — shipped (`[x]`).
- **Parked** — blocked / deferred / waiting on an owner decision.

## Format & rules

- One line per task: `- [ ] T-### | <title> | <tags>`
- Global ID counter (`T-001`, `T-002`, …). No per-column prefixes — moving a line never renames it. Next ID = max + 1.
- Status change = move the line to that column's section; when Done flip `[ ]` → `[x]`.
- Tag vocabulary (keep entries consistent):

| Tag | Meaning |
|---|---|
| `cost=cheap\|medium\|expensive` | LLM-burn gate. cheap = few/none LLM calls (deterministic plumbing); expensive = agentic/LLM-heavy. Pick `cheap` items in short windows. |
| `eff=XS\|S\|M\|L\|XL` | Effort estimate. |
| `doc=concepts/<file>.md` | Concept/design doc once Planned. |
| `deps=T-###` | Blocks-on dependency (repeatable). |
| `src=<file>` | Provenance if mined from an older doc (e.g. `critique.md`). |

- Keep titles short; push detail into the linked `doc=` or a concept file, not the line.
- `AGENTS.md` tells sessions to reconcile this file at the end of work.

## 🌱 Ideas

## 📋 Planned

- [ ] T-008 | Structured What→Why notes rail per section (value+delta, driver, OFF flag, reason), cached | doc=concepts/scorecard_roadmap.md | cost=medium | eff=L | deps=T-001
- [ ] T-009 | Summary tab: Question | Indicator | Callouts | doc=concepts/scorecard_roadmap.md | cost=cheap | eff=M | deps=T-001

## ✅ Ready

- [ ] T-004 | Deterministic per-section callout: fastest driver + laggard + missing-count | doc=concepts/scorecard_roadmap.md | cost=cheap | eff=S
- [ ] T-005 | Dimension guardrail: drop person/entity columns, ≤6 members | doc=concepts/scorecard_roadmap.md | cost=cheap | eff=S
- [ ] T-006 | Overall-row trend (last-N series, Overall only); skipped metrics → footnote | doc=concepts/scorecard_roadmap.md | cost=cheap | eff=M
- [ ] T-007 | Headline strip: deterministic one-line period summary | doc=concepts/scorecard_roadmap.md | cost=cheap | eff=S

## 🔨 Active

## 🏁 Done

- [x] T-001 | Scorecard tooltips = definition + basis (expose measurement in payload) | doc=concepts/scorecard_roadmap.md | cost=cheap | eff=S
- [x] T-002 | Unit normalization: fractional-change vs raw buckets | doc=concepts/scorecard_roadmap.md | cost=cheap | eff=S | (already present in fmtCell)
- [x] T-003 | Show executive_questions under each section header | doc=concepts/scorecard_roadmap.md | cost=cheap | eff=S

## ⏸️ Parked

- [ ] T-010 | Cell-level Ask-Why drill-down (scorecard analyze) | doc=concepts/scorecard_roadmap.md | cost=expensive | eff=XL | deps=T-006