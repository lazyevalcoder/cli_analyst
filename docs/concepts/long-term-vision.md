# Long-Term Vision — AI Data Analyst vs. Databricks Genie / AI·BI

A detailed competitive-gap note and the long-term plan to close the gaps we can close, double down on the moat we already have, and stay honest about the ones we should not chase.

**Status:** written 2026-08-02; companion to `roadmap.md`, `priority-compute-analyze-three-tier-split.md`, `metric-spec-v2-composable-operator-dsl.md`, `priority-value-verification-tier.md`. This is the "why and where we're going" layer above those.

---

## 1. The reference point (the only competitor we know, and it's the right one)

**Databricks Genie / AI/BI** is the flagship conversational-analytics product, and it is a fair mirror for what "AI data analysis" looks like as a product. Genie's actual shape (from Databricks docs):

- **Conversational analytics.** Natural language → SQL, run on governed tables, with follow-up questions, suggested next questions, and **clarifying questions** when the query is ambiguous.
- **Genie Spaces = a curated semantic context layer.** Declarative, shareable environments that define what data means: canonical metrics, business definitions, friendly column names, **value sampling**, entity lists / synonym dictionaries, expert-curated instructions.
- **Verifier + Accuracy Benchmarks.** A verifier agent validates results and triggers a re-run or a clarifying question; benchmarks are scored test questions (question → expected SQL) used to measure agent accuracy.
- **Feedback loop.** Query logs + user feedback refine the knowledge store, synonyms, and retraining.
- **AI/BI Dashboards.** AI-generated charts/dashboards and insight cards from natural language.
- **Multi-agent specialists.** Genie's architecture is multi-agent with specialists (geospatial, time-series, …) that can be added independently.
- **Governance.** Unity Catalog: RBAC, column-level masking, audit logging, governed metric definitions.
- **Scale + reach.** Runs on the lakehouse (distributed SQL, incremental refresh), embeds across web / notebook / Slack / chat, has an API, supports file upload for ad-hoc CSV/Excel.

Adjacent players to keep on the radar (so we never confuse "the market" with "Databricks"): Microsoft Copilot in Power BI (DAX semantics + NL), Snowflake Cortex Analyst, Google Looker/Vertex AI, dbt Semantic Layer (MetricFlow), AtScale, Atlan/Collibra (data-intelligence graphs). They all converge on the same two ideas: **a governed semantic layer** the AI reasons over, and **validation/trust tooling** around generated answers.

---

## 2. Capability matrix — Databricks Genie vs. Ours

| Capability | Databricks Genie / AI·BI | Ours today | Verdict |
|---|---|---|---|
| Conversational NL→query + clarification | ✅ chat, follow-ups, asks clarifying Qs | ❌ CLI only; no chat; compute never asks | **Lag** |
| Semantic context layer (canonical metrics, definitions, synonyms, value samples) | ✅ Genie Spaces + Unity Catalog semantics | ◐ KG + metric catalog + `measurement` strings; not curated/shared | **Lag** |
| Deterministic auditable compute | ◐ verifier is probabilistic | ✅ spec + template + validator; `basis`/`unit`/`verified` | **Lead** |
| Causal "why" explanation | ❌ semantic, not causal | ✅ structural + diagnostic KG → deep agentic analyze | **Lead** |
| Strategic framing (priorities, executive questions, briefing) | ❌ | ✅ | **Lead** |
| Dashboard / matrix deliverable | ✅ AI/BI Dashboards, insight cards | ◐ scorecard designed but unstarted; viewer = local file browser | **Lag** |
| Verification + accuracy benchmarks | ✅ verifier + Accuracy Benchmarks | ◐ pytest (dev-facing); verify tier parked | **Lag** |
| Feedback / learning from usage | ✅ query logs refine knowledge store | ◐ `metric edit` override; no learning loop | **Lag** |
| Governance (RBAC, masking, audit) | ✅ Unity Catalog | ◐ "local — nothing leaves your machine" is our substitute | **Positioning** |
| Multi-agent specialists (time-series/geo) | ✅ | ❌ one generic agentic `analyze` | **Lag (minor)** |
| Embedding / API / multi-platform | ✅ web, notebook, Slack, API | ❌ CLI | **Lag (minor)** |
| Scale (distributed SQL) | ✅ lakehouse | ◐ pandas/CSV | **Not a match** |

**Reading of the matrix:** we lead where it is hardest to copy (deterministic compute, causal knowledge-graph reasoning, consultant-grade framing), and we lag where it is cheapest for them and most visible to users (UI deliverables, feedback, trust tooling). Scale is the one column we should not chase.

---

## 3. What our moat actually is (protect this)

1. **Deterministic, auditable compute.** The LLM writes *specs*, a fixed template emits the pandas, the validator rejects bad specs, and every value carries `unit`, `basis`, `verified`. Genie's verifier is probabilistic; ours is structural for the value once the spec is accepted. This is the "Data → Scorecard → Pattern Detection → AI Explanation → Action" trust-layer principle from `roadmap.md`.
2. **Causal reasoning.** Structural KG (what exists) + diagnostic KG (chains, hypotheses, dimensions affecting) → the deep tier answers *why*, not just *what*. No competitor product ships causal chains derived from the data itself.
3. **Strategic framing.** Priorities → executive questions → KPIs + supporting metrics → briefing. A strategy-consultant layer, not a query surface.
4. **Local/private by default.** Data never leaves the machine. For regulated/security-conscious users this is a genuine selling point vs. a cloud Genie, and it is currently un-marketed.

---

## 4. The plan — 6 phases

### Phase 1 — Deliverable: scorecard → viewer (match AI/BI Dashboards) *[highest ROI]*
The roadmap already designs the **scorecard** (a dashboard matrix: outcomes as sections, dimensions as columns, filter-keyed cells) and its pipeline (`scorecard regenerate`: design → type confirmation → compute → persist → `scorecard analyze <n> [Region=East]` drill-down → briefing rework). It is unstarted.

- Land the scorecard pipeline per `roadmap.md` sequencing (prerequisite: O2/O3 priorities-quality, below).
- Extend `viewer.py` from a file-tree browser into a local matrix renderer: a `/api/scorecard` endpoint + a simple HTML table (sections = outcomes, rows = metrics, columns = dimension members with values). Keep it local and static-serving — no build step.
- `scorecard analyze` cell drill-down reuses `agentic_answer` with the cell value injected (already specified).

### Phase 2 — Trust: verifier + product-facing benchmarks (match verifier + Accuracy Benchmarks)
Land the parked verify tier (`priority-value-verification-tier.md`):

- **Persist the spec** on every value record (prerequisite; currently not stored).
- **L0** deterministic plausibility checks (non-negativity, share bounds, finiteness) — run automatically at the end of compute.
- **L1** independent re-derivation of simple specs in the parent process (1e-6 tolerance) — catches template regressions on real data.
- **L2** LLM semantic verifier (`verify_priority_prompt.md`): does the computed value match the measurement's intent + a sample of rows? Flag-only; no blind auto-repair.
- Add a **product-facing benchmark command** (`priorities benchmark`): a fixture registry of `(measurement → expected scalar)` scored against the DSL, surfaced as a per-dataset accuracy number — the Genie Accuracy Benchmarks analog, but for our spec DSL.

### Phase 3 — Feedback + semantic asset (match Genie Space + learning)
- Persist a curated per-project **measurement context**: canonical definitions, synonyms, value samples, dimension hints — derived from schema + KG + user `metric edit` overrides, injected into the spec prompt (synonym resolution at spec time).
- Make `metric edit` a **learning signal**: user-corrected definitions flow back into the measurement context and the few-shot bank (ties into O2/O3).
- Add a **clarifying-question flow**: when the validator cannot map a measurement to a spec, ask the user instead of silently marking `not_computable`. (Compute currently never asks — a direct Genie gap.)

### Phase 4 — Explainability: structured lineage (match "what was used and why")
- Add a `lineage` field to every value record: spec, filters, current/prior row counts, sample rows used.
- Render in `priorities show` / `priorities values` and the viewer.
- Every number becomes auditable end-to-end — compounding the deterministic-compute lead (basis strings today are a weak version of this).

### Phase 5 — Moat hardening (what Genie cannot do)
- Make the scorecard drill-down **causal**: `scorecard analyze <cell>` routes through the diagnostic KG (chains + hypotheses) rather than just re-running numbers.
- Codify the **local/private-by-default** posture as a first-class positioning + security note (README + docs), including "no data leaves the machine; no cloud dependency for compute."

### Phase 6 — Stretch: conversational + embed (only if we productize)
- Viewer gains a chat box → `analyze <question>` / follow-ups, with suggested questions sourced from the briefing.
- A thin local HTTP API so the CLI is scriptable / embeddable (the Genie embed + API analog).
- If ambition grows beyond a local tool, add governance positioning (roles, audit log of what each number used — largely already producible from Phase 4 lineage).

**Sequencing rule of thumb:** Phases 1–4 are "match"; 5–6 are "differentiate / ambitión." 1 and 2 are highest ROI and mostly reuse already-written design notes. 3 depends on O2/O3 few-shot bank being seeded. 4 is cheap and compounds everything.

---

## 5. Where we deliberately do NOT compete

- **Distributed SQL scale.** A local pandas tool will not (and should not) become a lakehouse. If a dataset outgrows memory, the answer is *export to a warehouse / let the pipeline point at their lakehouse* — not rebuild compute.
- **Enterprise governance stack** (RBAC, masking, audit trails at fleet scale). Our substitute is privacy-by-default and auditable lineage; we win the "I can't put my data in the cloud" segment, not the "I need fleet-wide governance" segment.

---

## 6. Dependencies on existing roadmap items

| This plan | Depends on | Status |
|---|---|---|
| Phase 1 scorecard | O2/O3 priorities-quality (validator + blueprint + few-shot bank) | **not started** |
| Phase 1 viewer | scorecard pipeline | **not started** |
| Phase 2 verify | spec persistence + compute tier (implemented) | compute ✅, verify 🅿️ parked |
| Phase 3 few-shot learning | O2/O3 few-shot bank | **not started** |
| Phase 3 clarifying flow | `_validate_spec` + compute loop (implemented) | compute ✅ |
| Phase 4 lineage | value-record shape in `compute_priority_values` (implemented) | ✅ shape exists |
| Phase 5 causal drill-down | diagnostic KG + scorecard | KG ✅, scorecard not started |

So the critical path to closing the biggest gaps is: **O2/O3 → scorecard → viewer → verify → lineage → feedback.** Phase 5 (causal) and Phase 2 (verify) can run in parallel with scorecard since they share the compute tier.

---

## 7. Open decisions (deferred)

1. **Ambition:** stay a local CLI (Phases 1–4) or path toward a productized web app (adds Phase 6 + governance positioning)?
2. **Ordering:** lead with the *deliverable* (scorecard/viewer — what users see) or the *trust* layer (verify/benchmark — what makes us defensible)? *Lean: deliverable-first; it is the most visible lag.*
3. **Semantic asset scope (Phase 3):** formal "Genie Space"-style curated context now, or keep it as persisted project state until the feedback loop proves value?
4. **Benchmark productization (Phase 2):** is a per-dataset accuracy score a real product surface for us, or should it stay a dev-facing harness?

---

## 8. Related docs

- `roadmap.md` — scorecard (dashboard matrix), Priorities Generation Quality (O2/O3), compute tier.
- `priority-compute-analyze-three-tier-split.md` — the three-tier compute/analyze/interpret model this vision extends.
- `metric-spec-v2-composable-operator-dsl.md` — the operator DSL the trust layer verifies.
- `priority-value-verification-tier.md` — the parked verify-tier plan Phase 2 lands.
- `Executive Scorecard Product Concept.md` / `Executive dashboard design framework.md` — the scorecard deliverable Phase 1 renders.
