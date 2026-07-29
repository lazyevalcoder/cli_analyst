import json
import re
from pathlib import Path
from typing import Optional


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class MetricCatalog:
    def __init__(self, entries: list[dict] = None):
        self._entries: list[dict] = entries or []

    # ---- persistence ----

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._entries, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "MetricCatalog":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(data if isinstance(data, list) else [])
        except (json.JSONDecodeError, OSError):
            return cls()

    # ---- build ----

    @classmethod
    def build_from(cls, priorities: list[dict]) -> "MetricCatalog":
        seen = set()
        entries = []
        for pri in priorities:
            pname = pri.get("name", "")
            for k in pri.get("kpis", []):
                kid = _slugify(k.get("name", ""))
                if kid and kid not in seen:
                    seen.add(kid)
                    entries.append({
                        "id": kid,
                        "name": k.get("name", ""),
                        "priority": pname,
                        "kind": "kpi",
                        "metric": k.get("metric", ""),
                        "description": k.get("description", ""),
                        "measurement": k.get("measurement", ""),
                        "influences": [],
                        "source": "llm-generated",
                    })
            for s in pri.get("supporting_metrics", []):
                sid = _slugify(s.get("name", ""))
                if sid and sid not in seen:
                    seen.add(sid)
                    inf = []
                    for ref in s.get("influences", []):
                        ref_id = _slugify(ref)
                        if ref_id:
                            inf.append(ref_id)
                    entries.append({
                        "id": sid,
                        "name": s.get("name", ""),
                        "priority": pname,
                        "kind": "supporting_metric",
                        "metric": s.get("metric", ""),
                        "description": s.get("description", ""),
                        "measurement": s.get("measurement", ""),
                        "influences": inf,
                        "source": "llm-generated",
                    })
        return cls(entries)

    # ---- queries ----

    @property
    def entries(self) -> list[dict]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def list(self, kind: str = None) -> list[dict]:
        if kind:
            return [e for e in self._entries if e.get("kind") == kind]
        return list(self._entries)

    def get(self, name_or_id: str) -> Optional[dict]:
        lower = name_or_id.strip().lower()
        for e in self._entries:
            if e.get("id") == lower or e.get("name", "").lower() == lower:
                return e
        try:
            idx = int(name_or_id) - 1
            if 0 <= idx < len(self._entries):
                return self._entries[idx]
        except ValueError:
            pass
        return None

    def get_by_priority(self, priority_name: str) -> list[dict]:
        lower = priority_name.strip().lower()
        return [e for e in self._entries if e.get("priority", "").lower() == lower]

    # ---- mutations ----

    def edit(self, name_or_id: str, field: str, value: str) -> bool:
        entry = self.get(name_or_id)
        if not entry:
            return False
        if field in ("description", "measurement", "metric"):
            entry[field] = value
            entry["source"] = "user-override"
            return True
        return False

    def reset(self, name_or_id: str, priorities: list[dict] = None) -> bool:
        old = self.get(name_or_id)
        if not old:
            return False
        if priorities:
            fresh = self.build_from(priorities)
            replacement = fresh.get(old["id"])
            if replacement:
                replacement["source"] = "llm-generated"
                replacement["analysis_summary"] = old.get("analysis_summary")
                replacement["analysis_slug"] = old.get("analysis_slug")
                self._entries[self._entries.index(old)] = replacement
                return True
        old["source"] = "llm-generated"
        return True

    # ---- formatting for prompts ----

    def format_for_prompt(self, name_or_id: str) -> str:
        entry = self.get(name_or_id)
        if not entry:
            return f"Metric '{name_or_id}' not found in catalog."
        return (
            f"--- {entry['name']} ---\n"
            f"Kind: {entry['kind']}\n"
            f"Source Column: {entry['metric']}\n"
            f"Description: {entry['description']}\n"
            f"Formula: {entry['measurement']}\n"
        )
