import cmd
import shlex
import shutil
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.analyst import agent
from src.analyst import builder
from src.analyst import llm
from src.analyst import viewer
from src.analyst.config import CONFIG
from src.analyst.graph import KnowledgeGraph, _slugify
from src.analyst.storage import append_jsonl, read_jsonl, save_json


def _make_slug(text: str) -> str:
    slug = _slugify(text, sep="-")
    return slug[:60] or "analysis"


def _unique_slug(base: str, existing: set) -> str:
    if base not in existing:
        return base
    for i in range(1, 100):
        candidate = f"{base}-{i}"
        if candidate not in existing:
            return candidate
    return base


def _show_turns(turns, max_chars=300):
    for i, t in enumerate(turns, 1):
        print(f"\n  --- Turn {i} ---")
        ts = t.get("timestamp", "")
        if ts:
            print(f"  [{ts}]")
        print(f"  Q: {t.get('question', '')}")
        summary = t.get('summary', '')
        truncated = len(summary) > max_chars
        print(f"  A: {summary[:max_chars]}{'...' if truncated else ''}")


class AnalystShell(cmd.Cmd):
    intro = "\nAI Data Analyst — Interactive Shell\nType help or ? to list commands."
    prompt = "(analyst) "

    def __init__(self, project):
        super().__init__()
        self.project = project
        self.df = None
        self._reasoning_framework = ""
        self._catalog = KnowledgeGraph()
        self._viewer_server = None
        self._load_state()
        self._check_llm()
        self._start_viewer()
        self._print_welcome()

    def onecmd(self, line):
        try:
            return super().onecmd(line)
        except KeyboardInterrupt:
            print("\n(Interrupted)")
            return False
        except Exception as e:
            print(f"\nError: {e}")
            return False

    def _print_welcome(self):
        p = self.project
        analyses = self._existing_analyses()

        print(f"\nProject: {p.name}")
        if p.is_data_loaded():
            loaded = "loaded" if self.df is not None else "file present"
            print(f"  Data: {p.data_path.name} ({loaded})")
        print(f"  Analyses: {len(analyses)}")

        if p.current_analysis:
            analysis_dir = p.analyses_dir / p.current_analysis
            turns = read_jsonl(analysis_dir / "turns.jsonl") if analysis_dir.exists() else []
            n = len(turns)
            first_q = turns[0]["question"][:80] if turns else ""
            print(f"  Current: {p.current_analysis} ({n} turn{'s' if n != 1 else ''})")
            if first_q:
                print(f"    Latest Q: {first_q[:80]}")

        # Contextual next-step hints
        if not p.is_data_loaded():
            print("  Next: use 'load <path>' to import a CSV file.")
        elif not p.has_structural_kg():
            print("  Next: use 'init' to build knowledge graphs.")
        else:
            if p.priorities:
                eq_total = sum(len(pri.get("executive_questions", [])) for pri in p.priorities)
                eq_info = f", {eq_total} questions" if eq_total else ""
                print(f"  Priorities: {len(p.priorities)} defined{eq_info}. Use 'priorities' to view.")
            if p.custom_instructions:
                print(f"  Custom instructions: {len(p.custom_instructions)} saved.")
            if p.current_analysis:
                print("  Use 'follow <question>' to continue this analysis.")
                print("  Use 'analyze <question>' to start a new analysis.")
            else:
                print("  Use 'analyze <question>' to start an analysis.")
                if not p.priorities:
                    print("  Use 'priorities' to generate strategic priorities first.")

    def _check_llm(self):
        if not llm.check_availability():
            print(f"Warning: LLM not available at {CONFIG.base_url}")
            print("  Graph building and deep analysis will fail.\n")

    def _load_state(self):
        if self.project.is_data_loaded():
            try:
                self.df = builder.load_csv(str(self.project.data_path))
                print(f"Reloaded {self.project.data_path.name}: {len(self.df)} rows, {len(self.df.columns)} columns")
            except Exception as e:
                print(f"Could not reload data: {e}")
        # Load cached reasoning framework — no LLM call
        if self.project.reasoning_framework:
            self._reasoning_framework = self.project.reasoning_framework

        # Load knowledge graph (backward compat with old metric_catalog.json)
        self._catalog = KnowledgeGraph.load(self.project.metric_catalog_path)

    def _require_data(self) -> bool:
        if self.df is None:
            print("No data loaded. Use 'load <path>' first.")
            return False
        return True

    def _require_skg(self) -> bool:
        if not self.project.has_structural_kg():
            print("Structural KG not built. Use 'init' first.")
            return False
        return True

    def _require_dkg(self) -> bool:
        if not self.project.has_diagnostic_kg():
            print("Diagnostic KG not built. Use 'init' first.")
            return False
        return True

    def _build_unified_graph(self):
        kg = KnowledgeGraph.build_from_kgs(
            self.project.structural_kg,
            self.project.diagnostic_kg,
            self.project.priorities,
        )
        kg.save(self.project.knowledge_graph_path)
        print(f"  Unified knowledge graph saved ({len(kg._nodes)} nodes, {len(kg._edges)} edges)")

    def _existing_analyses(self) -> set:
        if not self.project.analyses_dir.exists():
            return set()
        return {d.name for d in self.project.analyses_dir.iterdir() if d.is_dir()}

    # =========================================================
    #  Commands
    # =========================================================

    def do_status(self, arg):
        """status [llm] — Show project status (or LLM health check)"""
        sub = arg.strip().lower()

        if sub == "llm":
            ok = llm.check_availability()
            if ok:
                print("  LLM: available")
            else:
                print(f"  LLM: NOT available at {CONFIG.base_url}")
            return

        p = self.project
        print(f"Project: {p.name}")
        print(f"  Root: {p.root.resolve()}")
        if p.created_at:
            print(f"  Created: {p.created_at}")
        if p.updated_at:
            print(f"  Updated: {p.updated_at}")

        if p.is_data_loaded():
            loaded = "[x]" if self.df is not None else "(file present)"
            print(f"  Data: {p.data_path.name} {loaded}")
            if self.df is not None:
                print(f"    {len(self.df)} rows, {len(self.df.columns)} columns")
        else:
            print("  Data: —")

        print(f"  Schema: {'[x]' if p.has_schema() else '-'}")
        skg_n = len(p.structural_kg.get("nodes", []))
        skg_e = len(p.structural_kg.get("edges", []))
        print(f"  Structural KG: {'[x]' if p.has_structural_kg() else '-'} ({skg_n} nodes, {skg_e} edges)")
        dkg_c = len(p.diagnostic_kg.get("chains", []))
        dkg_h = len(p.diagnostic_kg.get("hypotheses", []))
        print(f"  Diagnostic KG: {'[x]' if p.has_diagnostic_kg() else '-'} ({dkg_c} chains, {dkg_h} hypotheses)")

        fw_avail = "[x]" if bool(p.reasoning_framework) else "-"
        fw_cached = "(disk)" if (p.metadata_dir / "reasoning_framework.json").exists() else ""
        print(f"  Framework: {fw_avail} {fw_cached}")
        if p.priorities:
            eq_total = sum(len(pri.get("executive_questions", [])) for pri in p.priorities)
            eq_info = f", {eq_total} executive questions" if eq_total else ""
            print(f"  Priorities: {len(p.priorities)} defined{eq_info}")
        else:
            print("  Priorities: -")
        print(f"  Custom instructions: {len(p.custom_instructions)} saved" if p.custom_instructions else "  Custom instructions: -")
        cat_n = len(self._catalog)
        if cat_n:
            kpi_n = len(self._catalog.list("kpi"))
            sm_n = len(self._catalog.list("supporting_metric"))
            print(f"  Metric Catalog: {cat_n} ({kpi_n} KPIs, {sm_n} supporting)")
        else:
            print(f"  Metric Catalog: -")

        analyses = self._existing_analyses()
        print(f"  Analyses: {len(analyses)}")
        if p.current_analysis:
            print(f"  Current: {p.current_analysis}")

    def do_welcome(self, arg):
        """welcome — Show welcome screen and next-step hints"""
        self._print_welcome()

    def do_help(self, arg):
        """help [<command>] — Show help (categorized by default)"""
        if arg.strip():
            super().do_help(arg)
            return

        categories = {
            "Setup":    ["load", "init", "rename"],
            "Knowledge": ["status", "view", "welcome", "priorities", "briefing", "metrics", "metric"],
            "Analysis":  ["analyze", "follow", "instructions"],
            "Review":    ["review", "analyses", "list", "export"],
            "Manage":    ["delete"],
            "Shell":     ["help", "quit"],
        }

        docstrings = {}
        for name in sorted(self.get_names()):
            if name[:3] == "do_":
                docstrings[name[3:]] = getattr(self, name).__doc__

        for cat, cmds in categories.items():
            print(f"\n  {cat}:")
            for cmd in cmds:
                doc = docstrings.get(cmd, "")
                if doc:
                    short = doc.split(" — ", 1)[-1].split("\n")[0]
                    print(f"    {cmd:12s} {short}")
            print()

    def do_load(self, arg):
        """load <path> — Load a CSV file into the project"""
        if not arg.strip():
            print("Usage: load <path>")
            return
        path = Path(arg.strip())
        if not path.exists():
            print(f"File not found: {path}")
            return

        if self.project.is_data_loaded():
            yn = input("Data already loaded. New data will invalidate existing KGs. Continue? (y/N): ").strip().lower()
            if yn != "y":
                print("Cancelled.")
                return

        suffix = path.suffix.lower()
        if suffix not in (".csv", ".tsv", ".txt"):
            print(f"Unsupported format: '{suffix}'. Only CSV files are supported.")
            return

        print(f"Loading {path.name}...", end="", flush=True)
        try:
            df = builder.load_csv(str(path))
        except Exception as e:
            print(f" failed: {e}")
            return
        print(f" {len(df)} rows, {len(df.columns)} columns")

        dest = self.project.data_dir / path.name
        if not dest.exists() or dest.resolve() != path.resolve():
            shutil.copy2(str(path), str(dest))

        self.df = df
        self.project.data_path = dest

        print("Extracting schema...")
        schema_dict = builder.build_schema_dict(df)
        self.project.schema = schema_dict

        # Invalidate stale KGs, priorities, cached framework
        self.project.structural_kg = {"nodes": [], "edges": []}
        self.project.diagnostic_kg = {"chains": [], "dimensions_affecting": {}, "hypotheses": []}
        self.project.priorities = []
        self.project.briefing_cache = {}
        self._reasoning_framework = ""

        print("Schema: " + ", ".join(c["name"] for c in schema_dict.get("columns", [])))
        self.project.save()
        print("Use 'init' to build knowledge graphs.")

    def do_init(self, arg):
        """init — Build schema + structural KG + diagnostic KG in one step"""
        if not self._require_data():
            return

        # Schema (extract locally, no LLM)
        if not self.project.has_schema():
            schema_dict = builder.build_schema_dict(self.df)
            self.project.schema = schema_dict
            print("Schema extracted.")
        schema_str = builder.extract_schema(self.df)

        # Structural KG
        if self.project.has_structural_kg():
            yn = input("Structural KG already exists. Rebuild? (y/N): ").strip().lower()
            if yn != "y":
                print("  Skipping SKG.")
            else:
                t0 = time.time()
                print("  Building structural KG...", end="", flush=True)
                kg = builder.build_structural_kg(schema_str)
                elapsed = time.time() - t0
                print(f" done ({elapsed:.1f}s)")
                print(f"  {len(kg.get('nodes', []))} nodes, {len(kg.get('edges', []))} edges")
                self.project.structural_kg = kg
        else:
            t0 = time.time()
            print("  Building structural KG...", end="", flush=True)
            kg = builder.build_structural_kg(schema_str)
            elapsed = time.time() - t0
            print(f" done ({elapsed:.1f}s)")
            print(f"  {len(kg.get('nodes', []))} nodes, {len(kg.get('edges', []))} edges")
            self.project.structural_kg = kg

        if not self.project.has_structural_kg():
            print("Cannot proceed without a structural KG.")
            self.project.save()
            return

        # Diagnostic KG
        if self.project.has_diagnostic_kg():
            yn = input("Diagnostic KG already exists. Rebuild? (y/N): ").strip().lower()
            if yn != "y":
                print("  Skipping DKG.")
            else:
                t0 = time.time()
                print("  Building diagnostic KG...", end="", flush=True)
                kg = builder.build_diagnostic_kg(self.project.structural_kg)
                elapsed = time.time() - t0
                print(f" done ({elapsed:.1f}s)")
                print(f"  {len(kg.get('chains', []))} chains, {len(kg.get('hypotheses', []))} hypotheses")
                self.project.diagnostic_kg = kg
        else:
            t0 = time.time()
            print("  Building diagnostic KG...", end="", flush=True)
            kg = builder.build_diagnostic_kg(self.project.structural_kg)
            elapsed = time.time() - t0
            print(f" done ({elapsed:.1f}s)")
            print(f"  {len(kg.get('chains', []))} chains, {len(kg.get('hypotheses', []))} hypotheses")
            self.project.diagnostic_kg = kg

        # Reasoning framework (cached to disk — no LLM call on next open)
        self._reasoning_framework = builder.get_full_reasoning_framework(
            schema_str, self.project.structural_kg, self.project.diagnostic_kg
        )
        self.project.reasoning_framework = self._reasoning_framework
        self.project.save()

        # Proactive: identify strategic priorities
        print("\n  Identifying strategic priorities...", end="", flush=True)
        try:
            priorities = builder.identify_priorities(schema_str, self.project.structural_kg, self.project.diagnostic_kg)
            if priorities:
                self.project.priorities = priorities
                self.project.save()
                self._catalog = KnowledgeGraph.build_from(priorities)
                self._catalog.save(self.project.metric_catalog_path)
                self._build_unified_graph()
                print(" done")
                print(f"\n  Strategic Priorities identified:")
                for i, p in enumerate(priorities, 1):
                    print(f"    {i}. {p.get('name', '?')} — {p.get('description', '')}")
                yn = input("\n  Generate strategic briefing based on these priorities? (Y/n): ").strip().lower()
                if yn != "n":
                    self.do_briefing("")
            else:
                print(" skipped (empty result)")
        except Exception as e:
            print(f" skipped ({e})")

        print("\nInitialization complete. Ready for analysis.")

    def do_view(self, arg):
        """view schema|entities|metrics|relationships|chains|hypotheses|data"""
        parts = shlex.split(arg)
        if not parts:
            print("Usage: view schema|entities|metrics|relationships|chains|hypotheses|data")
            return
        sub = parts[0].lower()

        if sub == "data":
            if self.df is None:
                print("No data loaded.")
                return
            print(self.df.head().to_string())
            return

        if sub == "schema":
            if not self.project.has_schema():
                print("No schema available. Load data first.")
                return
            cols = self.project.schema.get("columns", [])
            groups = {"numeric": [], "text": [], "datetime": [], "other": []}
            for c in cols:
                kind = c.get("kind", "other")
                groups.setdefault(kind, groups["other"]).append(c)
            for kind_label in ("numeric", "datetime", "text", "other"):
                items = groups.get(kind_label, [])
                if not items:
                    continue
                print(f"  [{kind_label.upper()}]")
                for c in items:
                    sample_str = ", ".join(repr(str(s)) for s in c.get("sample", []))
                    print(f"    {c['name']} ({c['dtype']}, {c.get('unique', 0)} unique)")
                    if sample_str:
                        print(f"      samples: [{sample_str}]")

        elif sub == "entities":
            if not self._require_skg():
                return
            nodes = [n for n in self.project.structural_kg.get("nodes", []) if n.get("type") == "entity"]
            if not nodes:
                print("  (no entities)")
            for n in nodes:
                print(f"  {n.get('label', n.get('id', '?'))}")

        elif sub == "metrics":
            if not self._require_skg():
                return
            nodes = [n for n in self.project.structural_kg.get("nodes", []) if n.get("type") == "measure"]
            if not nodes:
                print("  (no metrics)")
            for n in nodes:
                print(f"  {n.get('label', n.get('id', '?'))}")

        elif sub == "relationships":
            if not self._require_skg():
                return
            edges = self.project.structural_kg.get("edges", [])
            if not edges:
                print("  (no relationships)")
            for e in edges:
                print(f"  {e.get('source', '?')} --{e.get('relation', '?')}--> {e.get('target', '?')}")

        elif sub == "chains":
            if not self._require_dkg():
                return
            chains = self.project.diagnostic_kg.get("chains", [])
            if not chains:
                print("  (no chains)")
            for c in chains:
                path_str = " → ".join(c.get("path", []))
                print(f"  {c.get('metric', '?')}: {path_str}")
                if c.get("explanation"):
                    print(f"    {c['explanation']}")

        elif sub == "hypotheses":
            if not self._require_dkg():
                return
            hyps = self.project.diagnostic_kg.get("hypotheses", [])
            if not hyps:
                print("  (no hypotheses)")
            for h in hyps:
                print(f"  • {h}")

        else:
            print(f"Unknown view: {sub}")

    def do_priorities(self, arg):
        """priorities [regenerate|analyze|show] — Strategic priorities for this dataset

    Each priority contains 2-5 executive questions with KPIs and supporting metrics.

    Subcommands:
      priorities                           Show all priorities with executive questions
      priorities regenerate                Re-identify priorities from schema + KGs
      priorities analyze <n>               Run full analysis on priority #n
      priorities show <n>                  Show executive questions, KPIs, metrics for priority #n
        """
        parts = arg.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"

        # ----
        # regenerate
        # ----
        if sub == "regenerate":
            if not self._require_data() or not self.project.has_structural_kg():
                return
            schema_str = builder.extract_schema(self.df)
            print("  Regenerating strategic priorities...", end="", flush=True)
            try:
                priorities = builder.identify_priorities(schema_str, self.project.structural_kg, self.project.diagnostic_kg)
                if priorities:
                    self.project.priorities = priorities
                    self.project.save()
                    self._catalog = KnowledgeGraph.build_from(priorities)
                    self._catalog.save(self.project.metric_catalog_path)
                    self._build_unified_graph()
                    print(" done")
                else:
                    print(" skipped (empty result)")
            except Exception as e:
                print(f" failed: {e}")
            return

        # ----
        # analyze <n>
        # ----
        if sub == "analyze":
            if not self._require_data():
                return
            if not self.project.has_structural_kg():
                print("  Knowledge graphs not built. Run 'init' first.")
                return
            if not self.project.priorities:
                print("  No priorities defined. Use 'priorities regenerate' first.")
                return
            if len(parts) < 2:
                print("  Usage: priorities analyze <number>")
                print(f"  Priorities available: 1-{len(self.project.priorities)}")
                return
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(self.project.priorities):
                    print(f"  Invalid index. Use a number 1-{len(self.project.priorities)}.")
                    return
            except ValueError:
                print(f"  Usage: priorities analyze <number>")
                return

            pri = self.project.priorities[idx]
            pname = pri.get("name", f"priority-{idx+1}")
            eqs = pri.get("executive_questions", [])
            if eqs:
                eq_lines = [f"{j}. {eq.get('question', '?')}" for j, eq in enumerate(eqs, 1)]
                eq_section = " Executive questions:\n" + "\n".join(f"  - {l}" for l in eq_lines)
                question = (
                    f"Strategic analysis: {pri.get('description', pname)}. "
                    f"Focus areas: {pri.get('focus_areas', '')}.{eq_section}"
                ).strip()
            else:
                kpi_names = [k.get("name", "") for k in pri.get("kpis", [])]
                kpi_section = f" KPIs to track: {', '.join(kpi_names)}." if kpi_names else ""
                question = (
                    f"Strategic analysis: {pri.get('description', pname)}. "
                    f"Focus areas: {pri.get('focus_areas', '')}.{kpi_section}"
                ).strip()

            slug = _unique_slug(f"_priority-{_make_slug(pname)}", self._existing_analyses())
            analysis_dir = self.project.analyses_dir / slug
            analysis_dir.mkdir(parents=True, exist_ok=True)

            schema_str = builder.extract_schema(self.df)
            metric_brief = builder.format_priority_metric_brief(pri, self.project.diagnostic_kg)
            print(f"\n  Running analysis on priority [{pname}]...\n")

            try:
                answer = agent.agentic_answer(
                    question=question,
                    df=self.df,
                    schema=schema_str,
                    structural_kg=self.project.structural_kg,
                    diagnostic_kg=self.project.diagnostic_kg,
                    reasoning_framework=self._reasoning_framework,
                    context=None,
                    custom_instructions=self.project.custom_instructions,
                    graph=self._catalog,
                    metric_brief=metric_brief,
                )
            except KeyboardInterrupt:
                self.project.save()
                print("\n  Analysis interrupted.")
                return
            now = datetime.now().isoformat(timespec="seconds")
            append_jsonl(analysis_dir / "turns.jsonl", {"timestamp": now, "question": question, "summary": answer})

            pri["analysis_summary"] = answer
            pri["analysis_slug"] = slug
            self.project.save()

            print(f"\n  Priority [{pname}] analysis complete.")
            print(f"  Saved as '{slug}'. Use 'priorities show {idx+1}' or 'review {slug}' for details.\n")
            return

        # ----
        # show <n>
        # ----
        if sub == "show":
            if not self.project.priorities:
                print("  No priorities defined.")
                return
            if len(parts) < 2:
                print("  Usage: priorities show <number>")
                return
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(self.project.priorities):
                    print(f"  Invalid index. Use a number 1-{len(self.project.priorities)}.")
                    return
            except ValueError:
                print(f"  Usage: priorities show <number>")
                return

            pri = self.project.priorities[idx]
            pname = pri.get("name", f"priority-{idx+1}")
            summary = pri.get("analysis_summary", "")
            slug = pri.get("analysis_slug", "")
            eqs = pri.get("executive_questions", [])

            print(f"\n  Priority: {pname}")
            print(f"  {pri.get('description', '')}")
            if pri.get("focus_areas"):
                print(f"  Focus: {pri.get('focus_areas', '')}")

            if eqs:
                for j, eq in enumerate(eqs, 1):
                    qtext = eq.get("question", "?")
                    kpis = eq.get("kpis", [])
                    supporting = eq.get("supporting_metrics", [])
                    print(f"\n  Executive Question {j}: {qtext}")

                    if kpis:
                        print(f"    KPIs (outcome measures):")
                        for k in kpis:
                            kn = k.get("name", "?")
                            km = k.get("metric", "")
                            kd = k.get("description", "")
                            kmeas = k.get("measurement", "")
                            print(f"      {kn} ({km})")
                            print(f"        {kd}")
                            if kmeas:
                                print(f"        Measurement: {kmeas}")

                    if supporting:
                        print(f"    Supporting Metrics (driver/context):")
                        for s in supporting:
                            sn = s.get("name", "?")
                            sm = s.get("metric", "")
                            sd = s.get("description", "")
                            smeas = s.get("measurement", "")
                            inf = s.get("influences", [])
                            print(f"      {sn} ({sm})")
                            print(f"        {sd}")
                            if smeas:
                                print(f"        Measurement: {smeas}")
                            if inf:
                                print(f"        Influences: {', '.join(inf)}")
            else:
                kpis = pri.get("kpis", [])
                supporting = pri.get("supporting_metrics", [])
                if kpis:
                    print(f"\n  KPIs (outcome measures):")
                    for k in kpis:
                        kn = k.get("name", "?")
                        km = k.get("metric", "")
                        kd = k.get("description", "")
                        kmeas = k.get("measurement", "")
                        print(f"    {kn} ({km})")
                        print(f"      {kd}")
                        if kmeas:
                            print(f"      Measurement: {kmeas}")

                if supporting:
                    print(f"\n  Supporting Metrics (driver/context):")
                    for s in supporting:
                        sn = s.get("name", "?")
                        sm = s.get("metric", "")
                        sd = s.get("description", "")
                        smeas = s.get("measurement", "")
                        inf = s.get("influences", [])
                        print(f"    {sn} ({sm})")
                        print(f"      {sd}")
                        if smeas:
                            print(f"      Measurement: {smeas}")
                        if inf:
                            print(f"      Influences: {', '.join(inf)}")

                if not kpis and not supporting:
                    print(f"\n  (Run 'priorities regenerate' for KPI-enriched view)")

            if summary:
                print(f"\n  Analysis summary:")
                print(f"    {summary}")
                print(f"\n  Use 'review {slug}' for the full analysis.")
            else:
                print(f"\n  Not yet analyzed. Use 'priorities analyze {idx+1}' to run analysis.")
            return

        # ----
        # list (default)
        # ----
        p = self.project
        if not p.priorities:
            if p.has_structural_kg():
                print("  No priorities defined. Use 'priorities regenerate' to generate them.")
            else:
                print("  No priorities. Load data and run 'init' first.")
            return

        print(f"\n  Strategic Priorities for {p.name}:")
        for i, pri in enumerate(p.priorities, 1):
            name = pri.get("name", "?")
            desc = pri.get("description", "")
            focus = pri.get("focus_areas", "")
            analyzed = pri.get("analysis_summary", "")
            eqs = pri.get("executive_questions", [])

            print(f"\n  {i}. {name}")
            if desc:
                print(f"     {desc}")

            if eqs:
                for j, eq in enumerate(eqs, 1):
                    qtext = eq.get("question", "?")
                    kpi_names = [k.get("name", "?") for k in eq.get("kpis", [])]
                    sm_list = eq.get("supporting_metrics", [])
                    sm_names = [s.get("name", "?") for s in sm_list]
                    print(f"     Q{j}: {qtext}")
                    if kpi_names:
                        print(f"        KPIs: {', '.join(kpi_names)}")
                    if sm_names:
                        sm_str = ", ".join(sm_names[:3])
                        if len(sm_names) > 3:
                            sm_str += f" (+{len(sm_names) - 3} more)"
                        print(f"        Supporting: {sm_str}")
            else:
                kpis = pri.get("kpis", [])
                supporting = pri.get("supporting_metrics", [])
                if kpis:
                    kpi_str = ", ".join(k.get("name", "?") for k in kpis)
                    print(f"     KPIs: {kpi_str}")
                if supporting:
                    sm_top = supporting[:5]
                    sm_str = ", ".join(s.get("name", "?") for s in sm_top)
                    if len(supporting) > 5:
                        sm_str += f" (+{len(supporting) - 5} more)"
                    print(f"     Supporting Metrics: {sm_str}")
                if not kpis and not supporting:
                    print(f"     (\u2192 Run 'priorities regenerate' for KPI-enriched view)")

            if focus:
                print(f"     Focus: {focus}")
            if analyzed:
                slug_link = pri.get("analysis_slug", "?")
                print(f'     \u2192 \u2713 Analyzed (use "priorities show {i}" or "review {slug_link}")')
            else:
                print(f"     \u2192 Not yet analyzed (use 'priorities analyze {i}')")
        print()

    def do_metrics(self, arg):
        """metrics [kpis|supporting] — List metric catalog entries"""
        sub = arg.strip().lower()
        kind_map = {"kpis": "kpi", "supporting": "supporting_metric"}
        kind = kind_map.get(sub, None)

        entries = self._catalog.list(kind)
        if not entries:
            print("  Metric catalog is empty.")
            if self.project.priorities:
                print("  Use 'priorities regenerate' to rebuild.")
            else:
                print("  Use 'init' to generate priorities and populate the catalog.")
            return

        if kind:
            label = "KPIs" if kind == "kpi" else "Supporting Metrics"
            print(f"\n  {label} ({len(entries)}):")
        else:
            print(f"\n  Metric Catalog ({len(entries)} entries):")

        for e in entries:
            kind_label = "[KPI]" if e.get("type") == "kpi" else "[S]"
            source_mark = " (edited)" if e.get("source") == "user-override" else ""
            eq_text = f" | Q: {e.get('executive_question', '')[:60]}" if e.get("executive_question") else ""
            print(f"    {e.get('id', '?')}: {e.get('name', '?')} {kind_label} ({e.get('metric', '?')}){source_mark}")
            print(f"      Priority: {e.get('priority', '')}{eq_text}")
        print()

    def do_metric(self, arg):
        """metric show <name|#> | edit <name|#> <field> "<value>" | reset <name|#>

Manage individual metric definitions in the catalog.
Fields you can edit: measurement, description
        """
        parts = shlex.split(arg)
        if not parts:
            print("Usage: metric show|edit|reset <name|#> [field] [value]")
            return

        cmd = parts[0].lower()
        if len(parts) < 2:
            print("Missing metric name or number.")
            return

        target = parts[1]

        if cmd == "show":
            entry = self._catalog.get(target)
            if not entry:
                print(f"  Metric '{target}' not found.")
                return
            source_mark = " (overridden by user)" if entry.get("source") == "user-override" else " (LLM-generated)"
            print(f"\n  Name: {entry.get('name', '?')}{source_mark}")
            print(f"  Kind: {entry.get('type', '?')}")
            print(f"  Priority: {entry.get('priority', '')}")
            if entry.get("executive_question"):
                print(f"  Executive Question: {entry.get('executive_question', '')}")
            print(f"  Source Column: {entry.get('metric', '')}")
            print(f"  Description: {entry.get('description', '')}")
            print(f"  Measurement: {entry.get('measurement', '')}")
            inf = self._catalog._influence_names(entry["id"])
            if inf:
                print(f"  Influences: {', '.join(inf)}")
            print()

        elif cmd == "edit":
            if len(parts) < 4:
                print("Usage: metric edit <name|#> <field> \"<value>\"")
                print("  Fields: measurement, description")
                return
            field = parts[2].lower()
            if field not in ("measurement", "description"):
                print(f"  Cannot edit '{field}'. Allowed: measurement, description")
                return
            value = " ".join(parts[3:]).strip("\"'")
            if self._catalog.edit(target, field, value):
                self._catalog.save(self.project.metric_catalog_path)
                self._catalog.save(self.project.knowledge_graph_path)
                print(f"  Updated {field} for '{target}'.")
            else:
                print(f"  Metric '{target}' not found.")

        elif cmd == "reset":
            if self._catalog.reset(target, self.project.priorities):
                self._catalog.save(self.project.metric_catalog_path)
                self._catalog.save(self.project.knowledge_graph_path)
                print(f"  Reset '{target}' to LLM-generated version.")
            else:
                print(f"  Metric '{target}' not found.")

        else:
            print("Usage: metric show|edit|reset <name|#> [field] [value]")

    def do_graph(self, arg):
        """graph show|traverse <node> [relation] — Explore the knowledge graph

    Subcommands:
      graph show                        Show node/edge summary
      graph traverse <node> [relation]  Show connections for a node
        """
        parts = shlex.split(arg)
        if not parts:
            print("Usage: graph show|traverse <node> [relation]")
            return
        sub = parts[0].lower()

        if sub == "show":
            print(f"\n  Knowledge Graph:\n{self._catalog.format_summary()}\n")

        elif sub == "traverse":
            if len(parts) < 2:
                print("Usage: graph traverse <node> [relation]")
                return
            node = parts[1]
            relation = parts[2] if len(parts) > 2 else None
            print(f"\n{self._catalog.format_traverse(node, relation)}\n")

        else:
            print(f"Unknown graph subcommand: {sub}")

    def do_briefing(self, arg):
        """briefing [regenerate] — Show strategic briefing per priority"""
        if arg.strip().lower() == "regenerate":
            if not self._require_data() or not self.project.has_structural_kg():
                return
            if not self.project.priorities:
                print("  No priorities defined. Run 'priorities regenerate' first.")
                return
            schema_str = builder.extract_schema(self.df)
            print("  Generating strategic briefing...", end="", flush=True)
            try:
                briefing = builder.generate_briefing(schema_str, self.project.structural_kg, self.project.diagnostic_kg, self.project.priorities)
                self.project.briefing_cache = briefing
                self.project.save()
                print(" done")
            except Exception as e:
                print(f" failed: {e}")
                return
        else:
            briefing = self.project.briefing_cache
            if not briefing:
                print("  No cached briefing. Use 'briefing regenerate' to generate one.")
                return

        insights = briefing.get("priority_insights", []) if isinstance(briefing, dict) else []
        questions = briefing.get("suggested_questions", []) if isinstance(briefing, dict) else []

        if insights:
            print("\n  Strategic Briefing:")
            for item in insights:
                pname = item.get("priority", "")
                insight = item.get("insight", "")
                print(f"\n  [{pname}]")
                print(f"    {insight}")
        if questions:
            print("\n  Suggested starting questions:")
            for q in questions:
                print(f"    • {q}")
        print()

    def do_instructions(self, arg):
        """instructions [add|remove|clear] — Manage custom analysis instructions"""
        parts = arg.strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else "list"

        if cmd == "list" or not arg.strip():
            if not self.project.custom_instructions:
                print("  No custom instructions saved.")
                print("  Use 'instructions add \"your instruction\"' to add one.")
                return
            print(f"\n  Custom Instructions ({len(self.project.custom_instructions)}):")
            for i, instr in enumerate(self.project.custom_instructions, 1):
                print(f"  {i}. {instr}")
            print()

        elif cmd == "add":
            if len(parts) < 2:
                print("Usage: instructions add \"your instruction text\"")
                return
            instr = parts[1].strip().strip("\"'")
            if not instr:
                print("  Instruction cannot be empty.")
                return
            self.project.custom_instructions.append(instr)
            self.project.save()
            print(f"  Added instruction {len(self.project.custom_instructions)}: {instr[:80]}{'...' if len(instr) > 80 else ''}")

        elif cmd == "remove":
            if len(parts) < 2:
                print("Usage: instructions remove <number>")
                return
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(self.project.custom_instructions):
                    print(f"  Invalid index. Use 'instructions' to see the list.")
                    return
                removed = self.project.custom_instructions.pop(idx)
                self.project.save()
                print(f"  Removed instruction: {removed[:80]}{'...' if len(removed) > 80 else ''}")
            except ValueError:
                print("  Usage: instructions remove <number>")

        elif cmd == "clear":
            if not self.project.custom_instructions:
                print("  No instructions to clear.")
                return
            yn = input("  Clear all custom instructions? (y/N): ").strip().lower()
            if yn == "y":
                self.project.custom_instructions.clear()
                self.project.save()
                print("  All custom instructions cleared.")
            else:
                print("  Cancelled.")

        else:
            print("  Usage: instructions [add \"...\" | remove <n> | clear]")

    def do_analyze(self, arg):
        """analyze <question> — Start a new analysis"""
        if not arg.strip():
            print("Usage: analyze <question>")
            return
        try:
            args = shlex.split(arg)
        except ValueError:
            print("Error: invalid quoting")
            return
        question = " ".join(args)

        if not self._require_data():
            return
        if not self.project.has_schema():
            print("Schema not available. Load data first.")
            return

        # Load cached reasoning framework or rebuild if missing
        if not self._reasoning_framework:
            if self.project.reasoning_framework:
                self._reasoning_framework = self.project.reasoning_framework
            elif self.project.has_structural_kg():
                schema_str = builder.extract_schema(self.df)
                self._reasoning_framework = builder.get_full_reasoning_framework(
                    schema_str, self.project.structural_kg, self.project.diagnostic_kg
                )

        slug = _unique_slug(_make_slug(question), self._existing_analyses())
        analysis_dir = self.project.analyses_dir / slug
        analysis_dir.mkdir(parents=True, exist_ok=True)

        schema_str = builder.extract_schema(self.df)
        print(f"\nAnalysis slug: {slug}")
        print(f"Question: {question}\n")

        try:
            answer = agent.agentic_answer(
                question=question,
                df=self.df,
                schema=schema_str,
                structural_kg=self.project.structural_kg,
                diagnostic_kg=self.project.diagnostic_kg,
                reasoning_framework=self._reasoning_framework,
                context=None,
                custom_instructions=self.project.custom_instructions,
                graph=self._catalog,
            )
        except KeyboardInterrupt:
            self.project.save()
            print("\nAnalysis interrupted. Partial project state saved.")
            return

        now = datetime.now().isoformat(timespec="seconds")
        append_jsonl(analysis_dir / "turns.jsonl", {"timestamp": now, "question": question, "summary": answer})
        self.project.current_analysis = slug
        self.project.save()

        print(f"\nAnalyst: {answer}\n")
        if self.project.priorities:
            print("  Suggestions: use 'follow \"<question>\"' to dig deeper, or 'priorities' to see strategic areas.")
        print(f"(Saved as analysis '{slug}')")

    def do_follow(self, arg):
        """follow [<question>] — Follow up in the current analysis

        If no question is given, shows previous turns and prompts for one.
        """
        if not self._require_data():
            return
        if not self.project.current_analysis:
            print("No active analysis. Use 'analyze' first to start one.")
            return

        turns = read_jsonl(self.project.analyses_dir / self.project.current_analysis / "turns.jsonl")
        if not turns:
            print(f"Analysis '{self.project.current_analysis}' has no turns. Use 'analyze' instead.")
            return

        if not arg.strip():
            print(f"\nCurrent analysis: {self.project.current_analysis}")
            _show_turns(turns)
            print()
            question = input("Enter follow-up question: ").strip()
            if not question:
                print("Cancelled.")
                return
        else:
            try:
                args = shlex.split(arg)
            except ValueError:
                print("Error: invalid quoting")
                return
            question = " ".join(args)
            print(f"\nContinuing analysis: {self.project.current_analysis}")
            _show_turns(turns, max_chars=200)
            print(f"\nFollow-up: {question}")

        schema_str = builder.extract_schema(self.df)

        context = [{"question": t["question"], "summary": t["summary"]} for t in turns]

        # Load cached reasoning framework or rebuild if missing
        if not self._reasoning_framework:
            if self.project.reasoning_framework:
                self._reasoning_framework = self.project.reasoning_framework
            elif self.project.has_structural_kg():
                self._reasoning_framework = builder.get_full_reasoning_framework(
                    schema_str, self.project.structural_kg, self.project.diagnostic_kg
                )

        print()

        try:
            answer = agent.agentic_answer(
                question=question,
                df=self.df,
                schema=schema_str,
                structural_kg=self.project.structural_kg,
                diagnostic_kg=self.project.diagnostic_kg,
                reasoning_framework=self._reasoning_framework,
                context=context,
                custom_instructions=self.project.custom_instructions,
                graph=self._catalog,
            )
        except KeyboardInterrupt:
            self.project.save()
            print("\nAnalysis interrupted. Partial project state saved.")
            return

        now = datetime.now().isoformat(timespec="seconds")
        append_jsonl(
            self.project.analyses_dir / self.project.current_analysis / "turns.jsonl",
            {"timestamp": now, "question": question, "summary": answer},
        )
        self.project.save()

        print(f"\nAnalyst: {answer}\n")

    def do_analyses(self, arg):
        """analyses — List saved analyses"""
        existing = self._existing_analyses()
        if not existing:
            print("  (no analyses yet)")
            return
        for slug in sorted(existing):
            turns = read_jsonl(self.project.analyses_dir / slug / "turns.jsonl")
            n = len(turns)
            first_q = turns[0]["question"] if turns else "(empty)"
            last_q = turns[-1]["question"] if turns and len(turns) > 1 else None
            start_ts = turns[0].get("timestamp", "") if turns else ""
            marker = " ← current" if slug == self.project.current_analysis else ""
            print(f"  {slug}{marker}")
            ts_str = f" [{start_ts}]" if start_ts else ""
            if last_q:
                print(f"    {n} turn(s){ts_str}")
                print(f"    First: {first_q[:80]}{'...' if len(first_q) > 80 else ''}")
                print(f"    Latest: {last_q[:120]}{'...' if len(last_q) > 120 else ''}")
            else:
                print(f"    {n} turn(s){ts_str} | {first_q[:120]}{'...' if len(first_q) > 120 else ''}")

    def do_review(self, arg):
        """review [<slug>] — Show analysis turns (defaults to current)"""
        slug = arg.strip()
        if not slug:
            if not self.project.current_analysis:
                print("No current analysis. Use 'analyses' to list or 'analyze' to start one.")
                return
            slug = self.project.current_analysis
        analysis_dir = self.project.analyses_dir / slug
        if not analysis_dir.exists():
            print(f"Analysis '{slug}' not found.")
            return
        turns = read_jsonl(analysis_dir / "turns.jsonl")
        if not turns:
            print("  (empty)")
            return
        _show_turns(turns, max_chars=500)

    def do_rename(self, arg):
        """rename <new-name> — Rename the current project"""
        name = arg.strip()
        if not name:
            print("Usage: rename <new-name>")
            return
        if "/" in name or "\\" in name or not name.isprintable():
            print("Invalid project name.")
            return
        old_root = self.project.root
        new_root = old_root.parent / name
        if new_root.exists():
            print(f"Project '{name}' already exists.")
            return
        old_root.rename(str(new_root))
        self.project.name = name
        self.project.root = new_root
        self.project.save()
        print(f"Project renamed to '{name}'.")

    def do_list(self, arg):
        """list — List saved analyses (alias for analyses)"""
        self.do_analyses(arg)

    def do_delete(self, arg):
        """delete project <name>|analysis <slug> — Delete a project or analysis"""
        parts = shlex.split(arg)
        if len(parts) < 2:
            print("Usage: delete project <name>")
            print("       delete analysis <slug>")
            return
        kind, name = parts[0].lower(), parts[1]

        if kind == "project":
            root = Path("projects") / name
            if not root.exists():
                print(f"Project '{name}' not found.")
                return
            yn = input(f"Delete entire project '{name}'? This cannot be undone. (y/N): ").strip().lower()
            if yn != "y":
                print("Cancelled.")
                return
            shutil.rmtree(root)
            print(f"Project '{name}' deleted.")
            return

        if kind == "analysis":
            if not self.project.current_analysis and name == "current":
                name = self.project.current_analysis
            analysis_dir = self.project.analyses_dir / name
            if not analysis_dir.exists():
                print(f"Analysis '{name}' not found.")
                return
            yn = input(f"Delete analysis '{name}'? (y/N): ").strip().lower()
            if yn != "y":
                print("Cancelled.")
                return
            shutil.rmtree(analysis_dir)
            if self.project.current_analysis == name:
                self.project.current_analysis = None
            self.project.save()
            print(f"Analysis '{name}' deleted.")
            return

        print("Usage: delete project <name> | analysis <slug>")

    def do_export(self, arg):
        """export [<slug>] — Export analysis turns as markdown (defaults to current)"""
        slug = arg.strip()
        if not slug:
            if not self.project.current_analysis:
                print("No current analysis. Specify a slug or start an analysis first.")
                return
            slug = self.project.current_analysis
        analysis_dir = self.project.analyses_dir / slug
        if not analysis_dir.exists():
            print(f"Analysis '{slug}' not found.")
            return
        turns = read_jsonl(analysis_dir / "turns.jsonl")
        if not turns:
            print("  (empty)")
            return
        lines = [f"# Analysis: {slug}", f"", f"Project: {self.project.name}", f"", "---", ""]
        for i, t in enumerate(turns, 1):
            lines.append(f"## Turn {i}")
            lines.append(f"")
            lines.append(f"**Question:** {t.get('question', '')}")
            lines.append(f"")
            lines.append(t.get("summary", ""))
            lines.append("")
        md = "\n".join(lines)
        dest = analysis_dir / "export.md"
        dest.write_text(md, encoding="utf-8")
        print(f"Exported {len(turns)} turn(s) to {dest.resolve()}")

    def _start_viewer(self):
        if not self.project.root or not self.project.root.exists():
            return
        try:
            self._viewer_server = viewer.start_background(self.project.root.parent)
            print(f"  Web viewer: http://localhost:8081")
        except Exception as e:
            print(f"  Web viewer: failed to start ({e})")

    def do_quit(self, arg):
        """quit — Save and exit"""
        if self._viewer_server:
            self._viewer_server.shutdown()
        self.project.save()
        print("Project saved. Goodbye!")
        return True

    def do_EOF(self, arg):
        """Exit on Ctrl+Z/Ctrl+D"""
        return self.do_quit(arg)

    def emptyline(self):
        pass

    def default(self, line):
        print(f"Unknown command: {line}")
