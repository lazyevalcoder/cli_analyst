import argparse
import sys
from pathlib import Path

from project import init_project, open_project, ANALYST_META, PROJECTS_DIR
from shell import AnalystShell


def _scan_projects() -> list[Path]:
    projects_root = Path.cwd() / PROJECTS_DIR
    if not projects_root.exists():
        return []
    return sorted(
        p for p in projects_root.iterdir()
        if p.is_dir() and (p / ANALYST_META).exists()
    )


def _list_projects(projects: list[Path]) -> None:
    if projects:
        print("Available projects:")
        for i, p in enumerate(projects, 1):
            print(f"  {i}. {p.name}")
    else:
        print("No projects found in the current directory.")


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
