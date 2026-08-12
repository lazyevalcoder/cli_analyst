import cmd
import shlex
import shutil
import time
from datetime import datetime
from pathlib import Path

from src.analyst import agent, builder, llm, viewer
from src.analyst.config import CONFIG
from src.analyst.constants import STATUS_COMPUTED
from src.analyst.graph import KnowledgeGraph, slugify
from src.analyst.storage import append_jsonl, read_jsonl


def _make_slug(text: str) -> str:
    slug = slugify(text, sep="-")
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
        summary = t.get("summary", "")
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
                kpi_total = sum(len(pri.get("kpis", [])) for pri in p.priorities)
                kpi_info = f", {kpi_total} KPIs" if kpi_total else ""
                print(f"  Priorities: {len(p.priorities)} defined{kpi_info}. Use 'priorities' to view.")
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
            kpi_total = sum(len(pri.get("kpis", [])) for pri in p.priorities)
            kpi_info = f", {kpi_total} KPIs" if kpi_total else ""
            print(f"  Priorities: {len(p.priorities)} defined{kpi_info}")
        else:
            print("  Priorities: -")
        print(f"  Custom instructions: {len(p.custom_instructions)} saved" if p.custom_instructions else "  Custom instructions: -")
        cat_n = len(self._catalog)
        if cat_n:
            kpi_n = len(self._catalog.list_entries("kpi"))
            sm_n = len(self._catalog.list_entries("operational_metric")) + len(self._catalog.list_entries("supporting_metric"))
            print(f"  Metric Catalog: {cat_n} ({kpi_n} KPIs, {sm_n} operational)")
        else:
            print("  Metric Catalog: -")

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
            "Setup": ["load", "init", "rename"],
            "Knowledge": ["status", "view", "welcome", "priorities", "briefing", "metrics", "metric"],
            "Analysis": ["analyze", "follow", "instructions"],
            "Review": ["review", "analyses", "list", "export"],
            "Manage": ["delete"],
            "Shell": ["help", "quit"],
        }

        docstrings = {}
        for name in sorted(self.get_names()):
            if name[:3] == "do_":
                docstrings[name[3:]] = getattr(self, name).__doc__

        for cat, cmds in categories.items():
            print(f"\n  {cat}:")
            for command in cmds:
                doc = docstrings.get(command, "")
                if doc:
                    line = doc.split("\n")[0]
                    if " — " in line:
                        syntax, desc = line.split(" — ", 1)
                        short = f"{syntax} — {desc}"
                    else:
                        short = line
                    print(f"    {command:12s} {short}")
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
            framework = builder.identify_priorities(schema_str, self.project.structural_kg, self.project.diagnostic_kg, df=self.df)
            priorities = framework.get("priorities", [])
            if priorities:
                self.project.priorities = priorities
                self.project.save()
                self._catalog = KnowledgeGraph.build_from(priorities)
                self._catalog.save(self.project.metric_catalog_path)
                self._build_unified_graph()
                print(" done")
                excluded = framework.get("excluded_metrics", [])
                if excluded:
                    print("\n  Excluded metrics (failed the computability contract even after repair):")
                    for em in excluded:
                        print(f"    [{em.get('priority', '?')}] {em.get('name', '?')}: {em.get('reason', '')}")
                    print()
                print("\n  Strategic Priorities identified:")
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
            groups: dict[str, list] = {"numeric": [], "text": [], "datetime": [], "other": []}
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

    def _priority_values_record(self, pri: dict) -> dict | None:
        pv = self.project.priority_values or {}
        return pv.get("priorities", {}).get(pri.get("name", "")) or None

    def _stored_period(self) -> dict:
        """Reconstruct a period dict from the persisted machine-readable bounds."""
        pv = self.project.priority_values or {}
        p = pv.get("period") or {}
        return {
            "date_column": p.get("date_column"),
            "current_start": p.get("current_start"),
            "current_end": p.get("current_end"),
            "prior_start": p.get("prior_start"),
            "prior_end": p.get("prior_end"),
            "definition_text": pv.get("period_definition", ""),
        }

    def _priority_values_are_current(self, pri: dict) -> bool:
        rec = self._priority_values_record(pri)
        if rec is None:
            return False
        if (self.project.priority_values or {}).get("engine_version") != builder.COMPUTE_ENGINE_VERSION:
            return False
        if rec.get("engine_version") != builder.COMPUTE_ENGINE_VERSION:
            return False
        if rec.get("fingerprint") != builder.priority_fingerprint(pri):
            return False
        stored_fp = (self.project.priority_values or {}).get("data_fingerprint")
        if stored_fp != builder.data_fingerprint(self.df):
            return False
        stored_names = set(rec.get("values") or {})
        current_names = {str(k.get("name", "")) for _, k in builder._iter_priority_metrics(pri) if k.get("name")}
        if not current_names.issubset(stored_names):
            return False
        return True

    def _ensure_breakdowns(self, pri: dict, rec: dict) -> None:
        """Add the dimension breakdown matrix to a stored record (values must already be
        present). One LLM dimension-suggestion call + deterministic per-member values;
        no-op when the record already carries breakdowns. Persists when new."""
        if rec is None or not isinstance(rec, dict):
            return
        if rec.get("breakdowns") and rec.get("breakdown_dimensions"):
            return
        if self.df is None:
            return
        pname = pri.get("name", "")
        period = self._stored_period()
        if not period or not period.get("date_column"):
            return
        schema_str = builder.build_schema_with_enums(self.df)
        try:
            dim = builder.suggest_breakdown_dimensions(pri, self.df, schema_str, period)
        except Exception:
            dim = None
        if not dim:
            return
        try:
            dim["members"] = builder._dimension_members(self.df, dim["column"])
            bd = builder.compute_priority_breakdowns(pri, self.df, rec.get("values") or {}, period, dim)
        except Exception:
            bd = {}
        if not bd:
            return
        rec["breakdown_dimensions"] = [dim]
        rec["breakdowns"] = bd
        pv = dict(self.project.priority_values or {})
        pv.setdefault("priorities", {})[pname] = rec
        self.project.priority_values = pv
        self.project.save()

    def _ensure_priority_values(self, pri: dict) -> dict:
        """Auto-compute stored values if missing or stale (def fingerprint or data fingerprint).

        Resumes a partial run: already-recorded metrics (final status) are kept and only
        missing ones are computed. Persists after each executive question so Ctrl+C keeps
        completed questions. Also ensures the dimension breakdown matrix is present.
        """
        if self._priority_values_are_current(pri):
            rec = self._priority_values_record(pri)
            if rec is not None:
                self._ensure_breakdowns(pri, rec)
                return rec
        pname = pri.get("name", "")
        print(f"  Computing metric values for [{pname}]...")
        print(
            "  (This makes a few LLM calls and can take a few minutes. "
            f"Each LLM call times out after {CONFIG.llm_timeout_seconds}s if the model hangs.)",
            flush=True,
        )
        schema_str = builder.build_schema_with_enums(self.df)
        period = (getattr(self.project, "priority_framework", None) or {}).get("period") or {}

        existing: dict | None = None
        rec = self._priority_values_record(pri)
        pv = self.project.priority_values or {}
        base_current = (
            rec is not None
            and rec.get("engine_version") == builder.COMPUTE_ENGINE_VERSION
            and pv.get("engine_version") == builder.COMPUTE_ENGINE_VERSION
            and rec.get("fingerprint") == builder.priority_fingerprint(pri)
            and pv.get("data_fingerprint") == builder.data_fingerprint(self.df)
        )
        if base_current and rec is not None:
            existing = rec.get("values") or {}
            existing_skipped = rec.get("skipped") or {}
        else:
            existing_skipped = None

        def persist(result: dict):
            merged = dict(self.project.priority_values or {})
            merged["generated_at"] = result.get("generated_at")
            merged["data_fingerprint"] = result.get("data_fingerprint")
            merged["engine_version"] = result.get("engine_version")
            merged["period_definition"] = result.get("period_definition")
            merged["period"] = result.get("period")
            merged.setdefault("priorities", {}).update(result.get("priorities", {}))
            self.project.priority_values = merged
            self.project.save()

        result = builder.compute_priority_values(
            pri,
            self.df,
            schema_str,
            existing=existing,
            existing_skipped=existing_skipped,
            on_progress=persist,
            period=period,
        )
        persist(result)
        prec = result["priorities"].get(pname, {})
        self._ensure_breakdowns(pri, prec)
        print(f"  Stored {len(prec.get('values', {}))} computed value(s); {len(prec.get('skipped', {}))} skipped.")
        return prec

    def _print_priority_values(self, pri: dict):
        rec = self._priority_values_record(pri)
        if rec is None:
            print("  No stored values. Use 'priorities compute <n>'.")
            return
        values = rec.get("values", {})
        skipped = rec.get("skipped", {}) or {}
        period = (self.project.priority_values or {}).get("period_definition", "")
        print(f"\n  Stored values for [{pri.get('name', '')}]:")
        if period:
            print(f"  Period: {period}")
        if not values and not skipped:
            print("  (no metric values computed)")
        for mname, v in values.items():
            value = v.get("value")
            unit = v.get("unit", "")
            status = v.get("status", "")
            verified = "verified" if v.get("verified") else "UNVERIFIED"
            basis = v.get("basis", "")
            reason = v.get("reason_display") or builder.friendly_reason(v.get("reason", ""))
            print(f"    {mname}: {value} {unit}".rstrip())
            print(f"      [{status} | {verified}]")
            if basis:
                print(f"      basis: {basis}")
            if reason:
                print(f"      reason: {reason}")
        if skipped:
            print(f"\n  Skipped ({len(skipped)} not computable — use 'priorities skipped' for details):")
            for mname, s in skipped.items():
                print(f"    {mname}: {builder.friendly_reason(s.get('reason', ''))}")
        self._print_breakdown_matrix(rec)

    def _print_priority_skipped(self, pri: dict):
        """Compact skipping list: name + reason, no cluttered value records."""
        rec = self._priority_values_record(pri)
        if rec is None:
            print("  No stored values. Use 'priorities compute <n>' first.")
            return
        skipped = rec.get("skipped", {}) or {}
        if not skipped:
            print(f"  No skipped metrics for [{pri.get('name', '')}].")
            return
        print(f"\n  Skipped metrics for [{pri.get('name', '')}] ({len(skipped)}):")
        for mname, s in skipped.items():
            reason = s.get("reason", "")
            prim = s.get("missing_primitive")
            print(f"    - {mname}")
            print(f"        reason: {builder.friendly_reason(reason)}")
            if prim:
                print(f"        needs primitive: {prim}")
        print("  These metrics are honestly not computed — no substituted values.\n")

    def _print_breakdown_matrix(self, rec: dict) -> None:
        """Print the metrics-in-rows x members-in-columns breakdown table per dimension."""
        bdims = rec.get("breakdown_dimensions") or []
        for bdim in bdims:
            col = str(bdim.get("column", ""))
            bvals = (rec.get("breakdowns") or {}).get(col) or {}
            members = bdim.get("members") or []
            if not members or not bvals:
                continue
            print(f"\n  Breakdown by {col}:")
            widths = {m: max(len(m), 7) for m in members}
            print("    " + "Metric".ljust(38) + "".join(m.ljust(widths[m]) for m in members))
            any_nc = False
            for mname, cells in bvals.items():
                bym = {c.get("member"): c for c in cells}
                row = "    " + str(mname)[:36].ljust(38)
                for m in members:
                    c = bym.get(m)
                    if c and c.get("status") == STATUS_COMPUTED and c.get("delta") is not None:
                        row += f"{c['delta']:.3g}".ljust(widths[m])
                    else:
                        row += "—".ljust(widths[m])
                        any_nc = True
                print(row)
            if any_nc:
                print("    — = not computable for that member (no baseline / no data)")

    def _verify_priority_values(self, pri: dict) -> None:
        """Run the full verification stack for a priority and persist the verdicts.

        Layer 0 (plausibility) + Layer 1 (independent re-derivation) are deterministic
        and always run; Layer 2 (LLM semantic check) runs because the subcommand is the
        explicit request. Layer 2 can only unset `verified` / annotate — never set it.
        """
        rec = self._ensure_priority_values(pri)
        pname = pri.get("name", "")
        values = rec.get("values", {})
        if not values:
            print("  No stored values to verify.")
            return
        period = self._stored_period()
        schema_str = builder.build_schema_with_enums(self.df)
        print(f"  Verifying [{pname}]...")
        values, lsum = builder._verify_layers(values, self.df, period)
        print(builder._format_verify_summary(lsum))
        values = builder.verify_priority_values(pri, self.df, values, period, schema_str)
        checked = [v for v in values.values() if isinstance(v, dict) and v.get("status") == STATUS_COMPUTED]
        verified_n = sum(1 for v in checked if v.get("verified"))
        llm_failed = [m for m, v in values.items() if isinstance(v, dict) and (v.get("verification") or {}).get("llm_ok") is False]
        if llm_failed:
            print(f"  L2 semantic check flagged {len(llm_failed)} metric(s): {', '.join(sorted(llm_failed))}")
        self.project.priority_values = dict(self.project.priority_values or {})
        stored_rec = dict(rec or {})
        stored_rec.update(
            {
                "priority_ref": pname,
                "fingerprint": stored_rec.get("fingerprint", builder.priority_fingerprint(pri)),
                "engine_version": stored_rec.get("engine_version", builder.COMPUTE_ENGINE_VERSION),
                "values": values,
            }
        )
        self.project.priority_values.setdefault("priorities", {})[pname] = stored_rec
        self.project.save()
        print(
            f"  Verified {verified_n}/{len(checked)} computed metric(s). Use 'priorities values <n>' to review per-metric verdicts."
        )

    def do_priorities(self, arg):
        """priorities [regenerate|analyze|show|compute|verify|interpret|values] — Strategic priorities for this dataset

        Each priority is an outcome with executive questions (framing), delta-focused KPIs,
        and operational metrics (drivers) per KPI.

        Subcommands:
          priorities                           Show all priorities with executive questions
          priorities regenerate                Re-identify priorities from schema + KGs
          priorities analyze <n>               Run full (deep) analysis on priority #n
          priorities compute <n>               Resolve every metric to one scalar, persist values
          priorities verify <n>                Plausibility + re-derivation + LLM semantic check
          priorities interpret <n>             Quick one-call narration of stored values
          priorities values <n>                Print stored computed values (audit aid)
          priorities skipped <n>               Print metrics that could not be computed (no clutter)
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
            schema_str = builder.build_schema_with_enums(self.df)
            print("  Resolving anchoring time period...", end="", flush=True)
            try:
                period = builder.resolve_period(self.df, schema_str)
            except Exception as e:
                period = {}
                print(f" failed ({e}); proceeding unanchored.", flush=True)
            else:
                print(f" ok — {period.get('definition_text', '')}", flush=True)
            print("  Regenerating strategic priorities...", end="", flush=True)
            try:
                framework = builder.identify_priorities(
                    schema_str, self.project.structural_kg, self.project.diagnostic_kg, period=period, df=self.df
                )
                priorities = framework.get("priorities", [])
                if priorities:
                    self.project.priorities = priorities
                    self.project.priority_framework = {
                        "domain": framework.get("domain", ""),
                        "health_indicators": framework.get("health_indicators", []),
                        "period": period,
                        "excluded_metrics": framework.get("excluded_metrics", []),
                    }
                    self.project.priority_values = {}
                    self.project.save()
                    self._catalog = KnowledgeGraph.build_from(priorities)
                    self._catalog.save(self.project.metric_catalog_path)
                    self._build_unified_graph()
                    print(" done")
                    excluded = framework.get("excluded_metrics", [])
                    if excluded:
                        print("\n  Excluded metrics (failed the computability contract even after repair):")
                        for ex in excluded:
                            print(f"    [{ex.get('priority', '?')}] {ex.get('name', '?')}: {ex.get('reason', '')}")
                        print()
                    warnings = builder.scan_priority_viability(priorities, period, self.df)
                    if warnings:
                        print("\n  Viability scan (deterministic, pre-compute):")
                        for pri_name, mname, reason in warnings:
                            print(f"    [{pri_name}] {mname}: {reason}")
                        print("  These metrics will not compute as delta. Regenerate or edit them before 'priorities compute'.\n")
                    else:
                        print("  Viability scan: all metrics pass the deterministic data gate.")
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
                print("  Usage: priorities analyze <number>")
                return

            pri = self.project.priorities[idx]
            pname = pri.get("name", f"priority-{idx + 1}")
            eqs = pri.get("executive_questions", [])
            kpis = pri.get("kpis", [])
            eq_section = ""
            if eqs:
                eq_list = eqs if isinstance(eqs[0], str) else [eq.get("question", "?") for eq in eqs if isinstance(eq, dict)]
                if eq_list:
                    eq_lines = [f"{j}. {q}" for j, q in enumerate(eq_list, 1)]
                    eq_section = " Executive questions:\n" + "\n".join(f"  - {line}" for line in eq_lines)
            kpi_section = ""
            if kpis:
                kpi_names = [k.get("name", "") for k in kpis if k.get("name")]
                if kpi_names:
                    kpi_section = f" KPIs to track: {', '.join(kpi_names)}."
            question = (f"Strategic analysis: {pri.get('description', pname)}.{eq_section}{kpi_section}").strip()

            slug = _unique_slug(f"_priority-{_make_slug(pname)}", self._existing_analyses())
            analysis_dir = self.project.analyses_dir / slug
            analysis_dir.mkdir(parents=True, exist_ok=True)

            schema_str = builder.build_schema_with_enums(self.df)
            values_rec = self._ensure_priority_values(pri)
            metric_brief = builder.format_priority_metric_brief(
                pri,
                self.project.diagnostic_kg,
                values=(values_rec or {}).get("values") if values_rec else None,
            )
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
            print(f"  Saved as '{slug}'. Use 'priorities show {idx + 1}' or 'review {slug}' for details.\n")
            return

        # ----
        # compute <n>
        # ----
        if sub == "compute":
            if not self._require_data():
                return
            if not self.project.priorities:
                print("  No priorities defined. Use 'priorities regenerate' first.")
                return
            if len(parts) < 2:
                print("  Usage: priorities compute <number>")
                print(f"  Priorities available: 1-{len(self.project.priorities)}")
                return
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(self.project.priorities):
                    print(f"  Invalid index. Use a number 1-{len(self.project.priorities)}.")
                    return
            except ValueError:
                print("  Usage: priorities compute <number>")
                return
            pri = self.project.priorities[idx]
            try:
                self._ensure_priority_values(pri)
            except KeyboardInterrupt:
                self.project.save()
                print("\n  Compute interrupted.")
                return
            self._print_priority_values(pri)
            return

        # ----
        # verify <n>
        # ----
        if sub == "verify":
            if not self._require_data():
                return
            if not self.project.priorities:
                print("  No priorities defined. Use 'priorities regenerate' first.")
                return
            if len(parts) < 2:
                print("  Usage: priorities verify <number>")
                print(f"  Priorities available: 1-{len(self.project.priorities)}")
                return
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(self.project.priorities):
                    print(f"  Invalid index. Use a number 1-{len(self.project.priorities)}.")
                    return
            except ValueError:
                print("  Usage: priorities verify <number>")
                return
            pri = self.project.priorities[idx]
            self._verify_priority_values(pri)
            return

        # ----
        # interpret <n>
        # ----
        if sub == "interpret":
            if not self._require_data():
                return
            if not self.project.priorities:
                print("  No priorities defined. Use 'priorities regenerate' first.")
                return
            if len(parts) < 2:
                print("  Usage: priorities interpret <number>")
                print(f"  Priorities available: 1-{len(self.project.priorities)}")
                return
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(self.project.priorities):
                    print(f"  Invalid index. Use a number 1-{len(self.project.priorities)}.")
                    return
            except ValueError:
                print("  Usage: priorities interpret <number>")
                return
            pri = self.project.priorities[idx]
            pname = pri.get("name", f"priority-{idx + 1}")
            try:
                values_rec = self._ensure_priority_values(pri)
            except KeyboardInterrupt:
                self.project.save()
                print("\n  Compute interrupted.")
                return
            values = (values_rec or {}).get("values", {}) if values_rec else {}
            breakdowns = (values_rec or {}).get("breakdowns") or {}
            print(f"  Interpreting [{pname}]...")
            try:
                summary = builder.interpret_priority(pri, values, breakdowns)
            except KeyboardInterrupt:
                self.project.save()
                print("\n  Interpret interrupted.")
                return
            if builder._looks_like_reasoning(summary):
                cleaned = builder._clean_interpretation(summary)
                print("  Note: stripped LLM reasoning scaffolding from the interpretation.", flush=True)
                if not cleaned:
                    cleaned = summary
                summary = cleaned
            pri["interpretation_summary"] = summary
            pri["interpreted_at"] = datetime.now().isoformat(timespec="seconds")
            self.project.save()
            print(f"\n  {summary}\n")
            return

        # ----
        # values <n>
        # ----
        if sub == "values":
            if not self.project.priorities:
                print("  No priorities defined.")
                return
            if len(parts) < 2:
                print("  Usage: priorities values <number>")
                return
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(self.project.priorities):
                    print(f"  Invalid index. Use a number 1-{len(self.project.priorities)}.")
                    return
            except ValueError:
                print("  Usage: priorities values <number>")
                return
            self._print_priority_values(self.project.priorities[idx])
            return

        # ----
        # skipped <n>
        # ----
        if sub == "skipped":
            if not self.project.priorities:
                print("  No priorities defined.")
                return
            if len(parts) < 2:
                print("  Usage: priorities skipped <number>")
                return
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(self.project.priorities):
                    print(f"  Invalid index. Use a number 1-{len(self.project.priorities)}.")
                    return
            except ValueError:
                print("  Usage: priorities skipped <number>")
                return
            self._print_priority_skipped(self.project.priorities[idx])
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
                print("  Usage: priorities show <number>")
                return

            pri = self.project.priorities[idx]
            pname = pri.get("name", f"priority-{idx + 1}")
            summary = pri.get("analysis_summary", "")
            slug = pri.get("analysis_slug", "")
            eqs = pri.get("executive_questions", [])
            kpis = pri.get("kpis", [])
            fw = self.project.priority_framework or {}

            print(f"\n  Priority: {pname}")
            print(f"  {pri.get('description', '')}")
            if fw.get("domain"):
                print(f"  Domain: {fw.get('domain')}")

            if kpis:
                if eqs and not (eqs and isinstance(eqs[0], dict)):
                    print("\n  Executive questions (framing):")
                    for q in eqs:
                        print(f"    • {q}")
                sub_qs = pri.get("sub_questions", [])
                if sub_qs:
                    print("\n  Sub-questions (reasoning):")
                    for q in sub_qs:
                        if isinstance(q, dict):
                            q = q.get("question", "?")
                        print(f"    · {q}")
                for k in kpis:
                    kn = k.get("name", "?")
                    km = k.get("metric", "")
                    kd = k.get("description", "")
                    kmeas = k.get("measurement", "")
                    lenses = k.get("analytical_lenses", [])
                    ops = k.get("operational_metrics", [])
                    print(f"\n  KPI: {kn} ({km})")
                    if kd:
                        print(f"    {kd}")
                    if kmeas:
                        print(f"    Measurement: {kmeas}")
                    if lenses:
                        print(f"    Analytical lenses: {', '.join(lenses)}")
                    if ops:
                        print("    Operational metrics (drivers):")
                        for op in ops:
                            on = op.get("name", "?")
                            om = op.get("metric", "")
                            od = op.get("description", "")
                            omeas = op.get("measurement", "")
                            print(f"      {on} ({om})")
                            if od:
                                print(f"        {od}")
                            if omeas:
                                print(f"        Measurement: {omeas}")
            elif eqs and isinstance(eqs[0], dict):
                for j, eq in enumerate(eqs, 1):
                    qtext = eq.get("question", "?")
                    qkpis = eq.get("kpis", [])
                    qops = eq.get("supporting_metrics", [])
                    print(f"\n  Executive Question {j}: {qtext}")

                    if qkpis:
                        print("    KPIs (outcome measures):")
                        for k in qkpis:
                            kn = k.get("name", "?")
                            km = k.get("metric", "")
                            kd = k.get("description", "")
                            kmeas = k.get("measurement", "")
                            print(f"      {kn} ({km})")
                            if kd:
                                print(f"        {kd}")
                            if kmeas:
                                print(f"        Measurement: {kmeas}")

                    if qops:
                        print("    Operational Metrics (driver/context):")
                        for s in qops:
                            sn = s.get("name", "?")
                            sm = s.get("metric", "")
                            sd = s.get("description", "")
                            smeas = s.get("measurement", "")
                            inf = s.get("influences", [])
                            print(f"      {sn} ({sm})")
                            if sd:
                                print(f"        {sd}")
                            if smeas:
                                print(f"        Measurement: {smeas}")
                            if inf:
                                print(f"        Influences: {', '.join(inf)}")
            elif pri.get("kpis") or pri.get("supporting_metrics"):
                flat_kpis = pri.get("kpis", [])
                supporting = pri.get("supporting_metrics", [])
                if flat_kpis:
                    print("\n  KPIs (outcome measures):")
                    for k in flat_kpis:
                        kn = k.get("name", "?")
                        km = k.get("metric", "")
                        kd = k.get("description", "")
                        kmeas = k.get("measurement", "")
                        print(f"    {kn} ({km})")
                        if kd:
                            print(f"      {kd}")
                        if kmeas:
                            print(f"      Measurement: {kmeas}")

                if supporting:
                    print("\n  Operational Metrics (driver/context):")
                    for s in supporting:
                        sn = s.get("name", "?")
                        sm = s.get("metric", "")
                        sd = s.get("description", "")
                        smeas = s.get("measurement", "")
                        inf = s.get("influences", [])
                        print(f"    {sn} ({sm})")
                        if sd:
                            print(f"      {sd}")
                        if smeas:
                            print(f"      Measurement: {smeas}")
                        if inf:
                            print(f"      Influences: {', '.join(inf)}")
            else:
                print("\n  (Run 'priorities regenerate' for the KPI-enriched view)")

            rec = self._priority_values_record(pri)
            if rec:
                period = (self.project.priority_values or {}).get("period_definition", "")
                values = rec.get("values", {})
                skipped = rec.get("skipped", {}) or {}
                print("\n  Computed values:")
                if period:
                    print(f"    Period: {period}")
                for mname, v in values.items():
                    status = v.get("status", "")
                    verified = "verified" if v.get("verified") else "UNVERIFIED"
                    print(f"    {mname}: {v.get('value')} {v.get('unit', '')} [{status} | {verified}]".rstrip())
                if skipped:
                    print("\n  Skipped (not computable):")
                    for mname, s in skipped.items():
                        reason = s.get("reason", "")
                        print(
                            f"    {mname}: {builder.friendly_reason(reason)}"
                            f"{' [needs: ' + s['missing_primitive'] + ']' if s.get('missing_primitive') else ''}"
                        )
                    print("    (Use 'priorities skipped <n>' for the full list.)")

            interp = pri.get("interpretation_summary", "")
            if interp:
                print("\n  Interpretation summary:")
                print(f"    {interp}")

            if summary:
                print("\n  Analysis summary:")
                print(f"    {summary}")
                print(f"\n  Use 'review {slug}' for the full analysis.")
            else:
                print(f"\n  Not yet analyzed. Use 'priorities analyze {idx + 1}' to run analysis.")
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
        fw = p.priority_framework or {}
        if fw.get("domain"):
            print(f"  Domain: {fw.get('domain')}")
        selected = [h.get("name", "") for h in fw.get("health_indicators", []) if h.get("selected")]
        if selected:
            print(f"  Health indicators (selected): {', '.join(selected)}")
        for i, pri in enumerate(p.priorities, 1):
            name = pri.get("name", "?")
            desc = pri.get("description", "")
            analyzed = pri.get("analysis_summary", "")
            eqs = pri.get("executive_questions", [])
            kpis = pri.get("kpis", [])

            print(f"\n  {i}. {name}")
            if desc:
                print(f"     {desc}")

            if kpis:
                if eqs and not (eqs and isinstance(eqs[0], dict)):
                    for j, q in enumerate(eqs, 1):
                        print(f"     Q{j}: {q}")
                for k in kpis:
                    kn = k.get("name", "?")
                    op_names = [op.get("name", "?") for op in k.get("operational_metrics", [])]
                    line = f"     KPI: {kn}"
                    if op_names:
                        op_str = ", ".join(op_names[:3])
                        if len(op_names) > 3:
                            op_str += f" (+{len(op_names) - 3} more)"
                        line += f"  drivers: {op_str}"
                    print(line)
            elif eqs and isinstance(eqs[0], dict):
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
                        print(f"        Drivers: {sm_str}")
            else:
                flat_kpis = pri.get("kpis", [])
                supporting = pri.get("supporting_metrics", [])
                if flat_kpis:
                    kpi_str = ", ".join(k.get("name", "?") for k in flat_kpis)
                    print(f"     KPIs: {kpi_str}")
                if supporting:
                    sm_top = supporting[:5]
                    sm_str = ", ".join(s.get("name", "?") for s in sm_top)
                    if len(supporting) > 5:
                        sm_str += f" (+{len(supporting) - 5} more)"
                    print(f"     Drivers: {sm_str}")
                if not flat_kpis and not supporting:
                    print("     (\u2192 Run 'priorities regenerate' for the KPI-enriched view)")

            if analyzed:
                slug_link = pri.get("analysis_slug", "?")
                print(f'     \u2192 \u2713 Analyzed (use "priorities show {i}" or "review {slug_link}")')
            else:
                print(f"     \u2192 Not yet analyzed (use 'priorities analyze {i}')")
        print()

    def do_metrics(self, arg):
        """metrics [kpis|operational] — List metric catalog entries"""
        sub = arg.strip().lower()
        if sub in ("kpis", "kpi"):
            kind = "kpi"
        elif sub in ("operational", "operational_metrics", "supporting"):
            kind = "operational"
        else:
            kind = None

        if kind == "kpi":
            entries = self._catalog.list_entries("kpi")
        elif kind == "operational":
            entries = self._catalog.list_entries("operational_metric") + self._catalog.list_entries("supporting_metric")
        else:
            entries = self._catalog.list_entries()

        if not entries:
            print("  Metric catalog is empty.")
            if self.project.priorities:
                print("  Use 'priorities regenerate' to rebuild.")
            else:
                print("  Use 'init' to generate priorities and populate the catalog.")
            return

        if kind == "kpi":
            label = "KPIs"
        elif kind == "operational":
            label = "Operational Metrics"
        else:
            label = "Metric Catalog"

        print(f"\n  {label} ({len(entries)}):")

        for e in entries:
            kind_label = "[KPI]" if e.get("type") == "kpi" else "[Op]"
            source_mark = " (edited)" if e.get("source") == "user-override" else ""
            print(f"    {e.get('id', '?')}: {e.get('name', '?')} {kind_label} ({e.get('metric', '?')}){source_mark}")
            print(f"      Priority: {e.get('priority', '')}")
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
            kind_label = "Operational Metric" if entry.get("type") in ("operational_metric", "supporting_metric") else "KPI"
            print(f"\n  Name: {entry.get('name', '?')}{source_mark}")
            print(f"  Kind: {kind_label}")
            print(f"  Priority: {entry.get('priority', '')}")
            print(f"  Source Column: {entry.get('metric', '')}")
            print(f"  Description: {entry.get('description', '')}")
            print(f"  Measurement: {entry.get('measurement', '')}")
            inf = self._catalog._influence_names(entry["id"])
            if inf:
                print(f"  Influences: {', '.join(inf)}")
            print()

        elif cmd == "edit":
            if len(parts) < 4:
                print('Usage: metric edit <name|#> <field> "<value>"')
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
                briefing = builder.generate_briefing(
                    schema_str, self.project.structural_kg, self.project.diagnostic_kg, self.project.priorities
                )
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
                print('Usage: instructions add "your instruction text"')
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
                    print("  Invalid index. Use 'instructions' to see the list.")
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
            print('  Usage: instructions [add "..." | remove <n> | clear]')

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
        lines = [f"# Analysis: {slug}", "", f"Project: {self.project.name}", "", "---", ""]
        for i, t in enumerate(turns, 1):
            lines.append(f"## Turn {i}")
            lines.append("")
            lines.append(f"**Question:** {t.get('question', '')}")
            lines.append("")
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
            self._viewer_server = viewer.start_background(self.project.root.parent, project_name=self.project.name)
            print("  Web viewer: http://localhost:8081")
            print(f"  Scorecard: http://localhost:8081/scorecard (project: {self.project.name})")
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
