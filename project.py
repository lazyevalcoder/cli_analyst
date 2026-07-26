import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from storage import load_json, save_json

ANALYST_META = "analyst.json"
PROJECTS_DIR = "projects"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclass
class Project:
    name: str
    root: Path
    created_at: str = ""
    updated_at: str = ""
    data_path: Optional[Path] = None
    schema: dict = field(default_factory=dict)
    structural_kg: dict = field(default_factory=lambda: {"nodes": [], "edges": []})
    diagnostic_kg: dict = field(default_factory=lambda: {"chains": [], "dimensions_affecting": {}, "hypotheses": []})
    current_analysis: Optional[str] = None
    reasoning_framework: str = ""
    priorities: list = field(default_factory=list)
    custom_instructions: list[str] = field(default_factory=list)
    briefing_cache: dict = field(default_factory=dict)

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def graphs_dir(self) -> Path:
        return self.root / "graphs"

    @property
    def metadata_dir(self) -> Path:
        return self.root / "metadata"

    @property
    def analyses_dir(self) -> Path:
        return self.root / "analyses"

    def save(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.updated_at = now
        if not self.created_at:
            self.created_at = now
        save_json(self.graphs_dir / "structural.json", self.structural_kg)
        save_json(self.graphs_dir / "diagnostic.json", self.diagnostic_kg)
        save_json(self.metadata_dir / "schema.json", self.schema)
        save_json(self.metadata_dir / "reasoning_framework.json", {"text": self.reasoning_framework})
        save_json(self.metadata_dir / "priorities.json", self.priorities)
        save_json(self.metadata_dir / "custom_instructions.json", self.custom_instructions)
        save_json(self.metadata_dir / "briefing.json", self.briefing_cache)

        meta = {
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "data_path": str(self.data_path.relative_to(self.root)) if self.data_path else None,
            "current_analysis": self.current_analysis,
        }
        save_json(self.root / ANALYST_META, meta)

    def load(self) -> None:
        meta = load_json(self.root / ANALYST_META, {})
        self.name = meta.get("name", self.name)
        self.created_at = meta.get("created_at", "")
        self.updated_at = meta.get("updated_at", "")
        data_rel = meta.get("data_path")
        if data_rel:
            data_candidate = self.root / data_rel
            if data_candidate.exists():
                self.data_path = data_candidate
        self.current_analysis = meta.get("current_analysis")
        self.schema = load_json(self.metadata_dir / "schema.json", {})
        self.structural_kg = load_json(self.graphs_dir / "structural.json", {"nodes": [], "edges": []})
        self.diagnostic_kg = load_json(self.graphs_dir / "diagnostic.json",
                                       {"chains": [], "dimensions_affecting": {}, "hypotheses": []})
        self.reasoning_framework = load_json(self.metadata_dir / "reasoning_framework.json", {}).get("text", "")
        self.priorities = load_json(self.metadata_dir / "priorities.json", [])
        self.custom_instructions = load_json(self.metadata_dir / "custom_instructions.json", [])
        self.briefing_cache = load_json(self.metadata_dir / "briefing.json", {})

    def is_data_loaded(self) -> bool:
        return bool(self.data_path and self.data_path.exists())

    def has_schema(self) -> bool:
        return bool(self.schema.get("columns"))

    def has_structural_kg(self) -> bool:
        return bool(self.structural_kg.get("nodes"))

    def has_diagnostic_kg(self) -> bool:
        return bool(self.diagnostic_kg.get("chains"))


def init_project(name: str) -> Project:
    root = Path(PROJECTS_DIR) / name
    if root.exists():
        raise FileExistsError(f"Project '{name}' already exists at {root.resolve()}")
    _ensure_dir(root / "data")
    _ensure_dir(root / "graphs")
    _ensure_dir(root / "metadata")
    _ensure_dir(root / "analyses")
    project = Project(name=name, root=root)
    project.save()
    return project


def open_project(name: str) -> Project:
    root = Path(PROJECTS_DIR) / name
    if not root.exists():
        raise FileNotFoundError(f"Project '{name}' not found at {root.resolve()}")
    if not (root / ANALYST_META).exists():
        raise FileNotFoundError(f"Not a valid project: '{name}' (missing {ANALYST_META})")
    project = Project(name=name, root=root)
    project.load()
    return project
