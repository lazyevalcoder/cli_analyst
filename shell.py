import cmd
import re
import shlex
import shutil
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

    def _print_welcome(self):
        p = self.project
        print(f"\nProject: {p.name}")
        if p.is_data_loaded():
            loaded = "loaded" if self.df is not None else "file present"
            print(f"  Data: {p.data_path.name} ({loaded})")
        analyses = self._existing_analyses()
        print(f"  Analyses: {len(analyses)}")
        if p.current_analysis:
            analysis_dir = p.analyses_dir / p.current_analysis
            turns = read_jsonl(analysis_dir / "turns.jsonl") if analysis_dir.exists() else []
            n = len(turns)
            first_q = turns[0]["question"][:80] if turns else ""
            print(f"  Current: {p.current_analysis} ({n} turn{'s' if n != 1 else ''})")
            if first_q:
                print(f"    Latest Q: {first_q[:80]}")
            print("  Use 'follow <question>' to continue this analysis.")
            print("  Use 'analyze <question>' to start a new analysis instead.")
        elif self.df is not None:
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
        """Show project status"""
        p = self.project
        print(f"Project: {p.name}")
        print(f"  Root: {p.root.resolve()}")

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

        analyses = self._existing_analyses()
        print(f"  Analyses: {len(analyses)}")
        if p.current_analysis:
            print(f"  Current: {p.current_analysis}")

    def do_load(self, arg):
        """load <path> — Load a CSV file into the project"""
        if not arg.strip():
            print("Usage: load <path>")
            return
        path = Path(arg.strip())
        if not path.exists():
            print(f"File not found: {path}")
            return

        print(f"Loading {path.name}...", end="", flush=True)
        try:
            df = analyzer.load_csv(str(path))
        except Exception as e:
            print(f" error: {e}")
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

        print("Schema: " + ", ".join(c["name"] for c in schema_dict.get("columns", [])))
        self.project.save()

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
                print("Skipping SKG.")
            else:
                print("Building structural KG (LLM call)...", flush=True)
                kg = analyzer.build_structural_kg(schema_str)
                self.project.structural_kg = kg
                print(f"Done: {len(kg.get('nodes', []))} nodes, {len(kg.get('edges', []))} edges")
        else:
            print("Building structural KG (LLM call)...", flush=True)
            kg = analyzer.build_structural_kg(schema_str)
            self.project.structural_kg = kg
            print(f"Done: {len(kg.get('nodes', []))} nodes, {len(kg.get('edges', []))} edges")

        if not self.project.has_structural_kg():
            print("Cannot proceed without a structural KG.")
            self.project.save()
            return

        # Diagnostic KG
        if self.project.has_diagnostic_kg():
            yn = input("Diagnostic KG already exists. Rebuild? (y/N): ").strip().lower()
            if yn != "y":
                print("Skipping DKG.")
            else:
                print("Building diagnostic KG (LLM call)...", flush=True)
                kg = analyzer.build_diagnostic_kg(self.project.structural_kg)
                self.project.diagnostic_kg = kg
                print(f"Done: {len(kg.get('chains', []))} chains, {len(kg.get('hypotheses', []))} hypotheses")
        else:
            print("Building diagnostic KG (LLM call)...", flush=True)
            kg = analyzer.build_diagnostic_kg(self.project.structural_kg)
            self.project.diagnostic_kg = kg
            print(f"Done: {len(kg.get('chains', []))} chains, {len(kg.get('hypotheses', []))} hypotheses")

        # Reasoning framework (cached to disk — no LLM call on next open)
        self._reasoning_framework = analyzer.get_full_reasoning_framework(
            schema_str, self.project.structural_kg, self.project.diagnostic_kg
        )
        self.project.reasoning_framework = self._reasoning_framework
        self.project.save()
        print("Initialization complete. Ready for analysis.")

    def do_view(self, arg):
        """view schema|entities|metrics|relationships|chains|hypotheses"""
        parts = shlex.split(arg)
        if not parts:
            print("Usage: view schema|entities|metrics|relationships|chains|hypotheses")
            return
        sub = parts[0].lower()

        if sub == "schema":
            if not self.project.has_schema():
                print("No schema available. Load data first.")
                return
            col: dict
            for col in self.project.schema.get("columns", []):
                sample_str = ", ".join(repr(str(s)) for s in col.get("sample", []))
                print(f"  {col['name']} ({col['dtype']}, {col['kind']}, {col.get('unique', 0)} unique)")
                print(f"    samples: [{sample_str}]")

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
        print(f"\nStarting analysis: {question}\n")

        answer = analyzer.agentic_answer(
            question=question,
            df=self.df,
            schema=schema_str,
            structural_kg=self.project.structural_kg,
            diagnostic_kg=self.project.diagnostic_kg,
            reasoning_framework=self._reasoning_framework,
            context=None,
        )

        append_jsonl(analysis_dir / "turns.jsonl", {"question": question, "summary": answer})
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

        answer = analyzer.agentic_answer(
            question=question,
            df=self.df,
            schema=schema_str,
            structural_kg=self.project.structural_kg,
            diagnostic_kg=self.project.diagnostic_kg,
            reasoning_framework=self._reasoning_framework,
            context=context,
        )

        append_jsonl(
            self.project.analyses_dir / self.project.current_analysis / "turns.jsonl",
            {"question": question, "summary": answer},
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
            first_q = turns[0]["question"][:80] if turns else "(empty)"
            marker = " ← current" if slug == self.project.current_analysis else ""
            print(f"  {slug}{marker}")
            print(f"    {n} turn(s) | {first_q}")

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

    def do_list(self, arg):
        """list — List saved analyses (alias for analyses)"""
        self.do_analyses(arg)

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
