import cmd
import re
import shlex
import shutil
import time
from datetime import datetime
from pathlib import Path

import analyzer
import llm_client
import pandas as pd
from config import CONFIG
from storage import append_jsonl, read_jsonl, save_json


def _make_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
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
        self._load_state()
        self._check_llm()
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
        elif p.current_analysis:
            print("  Use 'follow <question>' to continue this analysis.")
            print("  Use 'analyze <question>' to start a new analysis.")
        else:
            print("  Use 'analyze <question>' to start an analysis.")

    def _check_llm(self):
        if not llm_client.check_availability():
            print(f"Warning: LLM not available at {CONFIG.base_url}")
            print("  Graph building and deep analysis will fail.\n")

    def _load_state(self):
        if self.project.is_data_loaded():
            try:
                self.df = analyzer.load_csv(str(self.project.data_path))
                print(f"Reloaded {self.project.data_path.name}: {len(self.df)} rows, {len(self.df.columns)} columns")
            except Exception as e:
                print(f"Could not reload data: {e}")
        # Load cached reasoning framework — no LLM call
        if self.project.reasoning_framework:
            self._reasoning_framework = self.project.reasoning_framework

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
            ok = llm_client.check_availability()
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
            "Knowledge": ["status", "view", "welcome"],
            "Analysis":  ["analyze", "follow"],
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
            df = analyzer.load_csv(str(path))
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
        schema_dict = analyzer.build_schema_dict(df)
        self.project.schema = schema_dict

        # Invalidate stale KGs and cached framework
        self.project.structural_kg = {"nodes": [], "edges": []}
        self.project.diagnostic_kg = {"chains": [], "dimensions_affecting": {}, "hypotheses": []}
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
            schema_dict = analyzer.build_schema_dict(self.df)
            self.project.schema = schema_dict
            print("Schema extracted.")
        schema_str = analyzer.extract_schema(self.df)

        # Structural KG
        if self.project.has_structural_kg():
            yn = input("Structural KG already exists. Rebuild? (y/N): ").strip().lower()
            if yn != "y":
                print("  Skipping SKG.")
            else:
                t0 = time.time()
                print("  Building structural KG...", end="", flush=True)
                kg = analyzer.build_structural_kg(schema_str)
                elapsed = time.time() - t0
                print(f" done ({elapsed:.1f}s)")
                print(f"  {len(kg.get('nodes', []))} nodes, {len(kg.get('edges', []))} edges")
                self.project.structural_kg = kg
        else:
            t0 = time.time()
            print("  Building structural KG...", end="", flush=True)
            kg = analyzer.build_structural_kg(schema_str)
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
                kg = analyzer.build_diagnostic_kg(self.project.structural_kg)
                elapsed = time.time() - t0
                print(f" done ({elapsed:.1f}s)")
                print(f"  {len(kg.get('chains', []))} chains, {len(kg.get('hypotheses', []))} hypotheses")
                self.project.diagnostic_kg = kg
        else:
            t0 = time.time()
            print("  Building diagnostic KG...", end="", flush=True)
            kg = analyzer.build_diagnostic_kg(self.project.structural_kg)
            elapsed = time.time() - t0
            print(f" done ({elapsed:.1f}s)")
            print(f"  {len(kg.get('chains', []))} chains, {len(kg.get('hypotheses', []))} hypotheses")
            self.project.diagnostic_kg = kg

        # Reasoning framework (cached to disk — no LLM call on next open)
        self._reasoning_framework = analyzer.get_full_reasoning_framework(
            schema_str, self.project.structural_kg, self.project.diagnostic_kg
        )
        self.project.reasoning_framework = self._reasoning_framework
        self.project.save()
        print("Initialization complete. Ready for analysis.")

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
                schema_str = analyzer.extract_schema(self.df)
                self._reasoning_framework = analyzer.get_full_reasoning_framework(
                    schema_str, self.project.structural_kg, self.project.diagnostic_kg
                )

        slug = _unique_slug(_make_slug(question), self._existing_analyses())
        analysis_dir = self.project.analyses_dir / slug
        analysis_dir.mkdir(parents=True, exist_ok=True)

        schema_str = analyzer.extract_schema(self.df)
        print(f"\nAnalysis slug: {slug}")
        print(f"Question: {question}\n")

        try:
            answer = analyzer.agentic_answer(
                question=question,
                df=self.df,
                schema=schema_str,
                structural_kg=self.project.structural_kg,
                diagnostic_kg=self.project.diagnostic_kg,
                reasoning_framework=self._reasoning_framework,
                context=None,
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

        schema_str = analyzer.extract_schema(self.df)

        context = [{"question": t["question"], "summary": t["summary"]} for t in turns]

        # Load cached reasoning framework or rebuild if missing
        if not self._reasoning_framework:
            if self.project.reasoning_framework:
                self._reasoning_framework = self.project.reasoning_framework
            elif self.project.has_structural_kg():
                self._reasoning_framework = analyzer.get_full_reasoning_framework(
                    schema_str, self.project.structural_kg, self.project.diagnostic_kg
                )

        print()

        try:
            answer = analyzer.agentic_answer(
                question=question,
                df=self.df,
                schema=schema_str,
                structural_kg=self.project.structural_kg,
                diagnostic_kg=self.project.diagnostic_kg,
                reasoning_framework=self._reasoning_framework,
                context=context,
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

    def do_quit(self, arg):
        """quit — Save and exit"""
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
