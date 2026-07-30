# Critique: AI Data Analyst — RevOps Perspective

## Current State (After MECE Prompt Fix)

**Priority framework after `priorities regenerate` with new prompt rules:**

1. Revenue Growth & Volume Dynamics
2. Profitability & Cost Structure Health
3. Customer Segment Value & Retention
4. Operational Fulfillment Efficiency

The naming is professional, the KPIs are precise, and the four priorities now cover genuinely distinct domains with no overlap. The new "Customer Segment Value & Retention" fills a gap the old framework missed.

## Severity Assessment

| Sev | # | Issue | Detail |
|---|---|---|---|
| 🟢 | 1 | **MECE — clean separation.** Priorities cover distinct domains: top-line, margins, customers, operations. No overlap. | Fixed by prompt rules. |
| 🟢 | 2 | **Analysis quality is strong.** Priority 1's stored analysis includes real data: $8.95M revenue, YoY growth rates, volume/price decomposition with actual percentages. | The 4-phase pipeline produces genuine output. |
| 🟡 | 3 | **Self-referencing influences persist.** 4 of 8 KPIs have `influences: ["self"]` — Customer Retention Cohort Performance, Segment Value Concentration, Fulfillment Cost Efficiency, Transit Time Reliability. | Prompt rule "no self-references" didn't fully take. Need code-level strip. |
| 🟡 | 4 | **Priorities 3 & 4 have no analysis yet.** A RevOps manager would see empty summaries and wonder if they're half-baked. | Run `priorities analyze` on them. |
| 🟡 | 5 | **No confidence scoring.** DKG causal chains have no confidence/evidence metadata. Manager can't judge reliability. | Needs code change. |
| 🟡 | 6 | **No proactive recommendations.** System answers questions but doesn't drive action. The risk analysis in sample data shows this *can* happen, but it's not systematic. | Needs code change. |
| 🔴 | 7 | **Slow per-analysis wait.** `analyze` blocks terminal 30-90s with no streaming. Non-technical users feel every second. | Needs streaming support. |
| 🔴 | 8 | **No visualization, no export.** All output is text. Can't generate charts, PDFs, or slides from findings. | Needs new export commands. |
| 🟡 | 9 | **Unified KG is redundant.** Same data in structural.json + diagnostic.json + metric_catalog.json + knowledge_graph.json. Traverse_graph only does 1-hop. | Needs consolidation. |
| 🟢 | 10 | **Custom instructions exist** but no onboarding prompts user to set them. Few know about the feature. | Needs UX nudge. |

## What Would Earn a "Yes" from a RevOps Manager

- An executive summary on open: "$8.9M revenue, 48 months, 4 regions, 48% of orders lose money"
- Exportable reports (PDF/slides at minimum)
- Ability to add/customize priorities, not just edit formulas
- Proactive briefing that diagnoses the business, not just lists categories
- Visual output (even ASCII sparklines)

## Verdict

The MECE fix improved the framework meaningfully — the four priorities are now genuinely professional-grade. The analysis output (when run) produces real business intelligence. The remaining issues are mostly UX polish and code-level enforcement of constraints the prompt can't guarantee. The gap between "capable analysis engine" and "production RevOps tool" is narrowing but still significant.
