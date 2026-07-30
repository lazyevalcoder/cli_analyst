import argparse
import sys
from pathlib import Path

from src.analyst.project import init_project, open_project, ANALYST_META, PROJECTS_DIR
from src.analyst.shell import AnalystShell
from src.analyst.storage import load_json


def _scan_projects() -> list[Path]:
    projects_root = Path.cwd() / PROJECTS_DIR
    if not projects_root.exists():
        return []
    return sorted(
        p for p in projects_root.iterdir()
        if p.is_dir() and (p / ANALYST_META).exists()
    )


def _project_summary(root: Path) -> dict:
    meta = load_json(root / ANALYST_META, {})
    data_rel = meta.get("data_path", "")
    data_file = Path(data_rel).name if data_rel else "-"

    schema = load_json(root / "metadata" / "schema.json", {})
    skg = load_json(root / "graphs" / "structural.json", {})
    dkg = load_json(root / "graphs" / "diagnostic.json", {})

    analyses_dir = root / "analyses"
    n_analyses = len([d for d in analyses_dir.iterdir() if d.is_dir()]) if analyses_dir.exists() else 0

    return {
        "data": data_file,
        "schema": "[x]" if bool(schema.get("columns")) else "",
        "skg_n": str(len(skg.get("nodes", []))) if skg.get("nodes") else "",
        "dkg_c": str(len(dkg.get("chains", []))) if dkg.get("chains") else "",
        "analyses": str(n_analyses) if n_analyses else "",
    }


def _list_projects(projects: list[Path]) -> None:
    if not projects:
        print("No projects found.")
        return
    print(f"  {'#':>2s}  {'Name':20s}  {'Data':22s}  {'Sch':4s}  {'SKGn':5s}  {'DKGc':5s}  {'Anls':4s}")
    print("  " + "-" * 70)
    for i, p in enumerate(projects, 1):
        s = _project_summary(p)
        print(f"  {i:>2d}  {p.name:20s}  {s['data']:22s}  {s['schema']:>4s}  {s['skg_n']:>5s}  {s['dkg_c']:>5s}  {s['analyses']:>4s}")


def _interactive() -> None:
    projects = _scan_projects()
    while True:
        print()
        _list_projects(projects)
        print("  n. Create a new project")
        print("  q. Quit")
        choice = input("\nEnter your choice: ").strip().lower()

        if choice == "q":
            print("Goodbye.")
            sys.exit(0)

        if choice == "n":
            name = input("Project name: ").strip()
            if not name:
                print("Name cannot be empty.")
                continue
            try:
                project = init_project(name)
                print(f"Project '{name}' created.")
                AnalystShell(project).cmdloop()
                return
            except FileExistsError as e:
                print(f"Error: {e}")
                continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(projects):
                name = projects[idx].name
                project = open_project(name)
                print(f"Project '{name}' opened.")
                AnalystShell(project).cmdloop()
                return
            print(f"Enter a number 1-{len(projects)}, n, or q.")
        except ValueError:
            print("Enter a number, n, or q.")


def main():
    parser = argparse.ArgumentParser(prog="analyst", description="AI Data Analyst")
    parser.add_argument(
        "action",
        nargs="?",
        choices=["init", "open", "list"],
        help="Create or open a project",
    )
    parser.add_argument("name", nargs="?", help="Project name / directory")

    args = parser.parse_args()

    if args.action is None:
        _interactive()
        return

    if args.action == "list":
        _list_projects(_scan_projects())
        return

    if args.name is None:
        parser.error(f"'{args.action}' requires a project name")

    try:
        if args.action == "init":
            project = init_project(args.name)
            print(f"Project '{args.name}' created.")
        elif args.action == "open":
            project = open_project(args.name)
            print(f"Project '{args.name}' opened.")
    except (FileExistsError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    AnalystShell(project).cmdloop()


if __name__ == "__main__":
    main()
