from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class KnowledgeGraph:
    def __init__(self, nodes: list[dict] = None, edges: list[dict] = None):
        self._nodes: list[dict] = nodes or []
        self._edges: list[dict] = edges or []

    # ---- persistence ----

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"nodes": self._nodes, "edges": self._edges}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "KnowledgeGraph":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return cls._from_entries(data)
            if isinstance(data, dict):
                nodes = data.get("nodes", [])
                edges = data.get("edges", [])
                return cls(
                    nodes if isinstance(nodes, list) else [],
                    edges if isinstance(edges, list) else [],
                )
        except (json.JSONDecodeError, OSError):
            pass
        return cls()

    @classmethod
    def _from_entries(cls, entries: list[dict]) -> "KnowledgeGraph":
        nodes = []
        edges = []
        for e in entries:
            node = {
                "id": e.get("id", ""),
                "name": e.get("name", ""),
                "type": "kpi" if e.get("kind") == "kpi" else "supporting_metric",
                "priority": e.get("priority", ""),
                "metric": e.get("metric", ""),
                "description": e.get("description", ""),
                "measurement": e.get("measurement", ""),
                "source": e.get("source", "llm-generated"),
            }
            nodes.append(node)
            for target_id in e.get("influences", []):
                edges.append({
                    "source": node["id"],
                    "target": target_id,
                    "relation": "INFLUENCES",
                })
        return cls(nodes, edges)

    # ---- build from priorities (replaces MetricCatalog.build_from) ----

    @classmethod
    def build_from(cls, priorities: list[dict]) -> "KnowledgeGraph":
        seen = set()
        nodes = []
        edges = []
        for pri in priorities:
            pname = pri.get("name", "")
            for k in pri.get("kpis", []):
                kid = _slugify(k.get("name", ""))
                if kid and kid not in seen:
                    seen.add(kid)
                    nodes.append({
                        "id": kid,
                        "name": k.get("name", ""),
                        "type": "kpi",
                        "priority": pname,
                        "metric": k.get("metric", ""),
                        "description": k.get("description", ""),
                        "measurement": k.get("measurement", ""),
                        "source": "llm-generated",
                    })
            for s in pri.get("supporting_metrics", []):
                sid = _slugify(s.get("name", ""))
                if sid and sid not in seen:
                    seen.add(sid)
                    nodes.append({
                        "id": sid,
                        "name": s.get("name", ""),
                        "type": "supporting_metric",
                        "priority": pname,
                        "metric": s.get("metric", ""),
                        "description": s.get("description", ""),
                        "measurement": s.get("measurement", ""),
                        "source": "llm-generated",
                    })
                    for ref in s.get("influences", []):
                        ref_id = _slugify(ref)
                        if ref_id:
                            edges.append({
                                "source": sid,
                                "target": ref_id,
                                "relation": "INFLUENCES",
                            })
        return cls(nodes, edges)

    # ---- build unified graph from all sources ----

    @classmethod
    def build_from_kgs(cls, structural_kg: dict, diagnostic_kg: dict, priorities: list[dict]) -> "KnowledgeGraph":
        graph = cls.build_from(priorities)
        existing_ids = {n["id"] for n in graph._nodes}

        for node in structural_kg.get("nodes", []):
            nid = node.get("id", "")
            if nid and nid not in existing_ids:
                graph._nodes.append({
                    "id": nid,
                    "name": node.get("label", nid),
                    "type": node.get("type", "unknown"),
                    "source": "structural-kg",
                })
                existing_ids.add(nid)

        for edge in structural_kg.get("edges", []):
            graph._edges.append({
                "source": edge.get("source", ""),
                "target": edge.get("target", ""),
                "relation": edge.get("relation", ""),
            })

        for chain in diagnostic_kg.get("chains", []):
            path = chain.get("path", [])
            for i in range(len(path) - 1):
                src = _slugify(path[i])
                tgt = _slugify(path[i + 1])
                graph._edges.append({
                    "source": src,
                    "target": tgt,
                    "relation": "DERIVED_FROM",
                })

        return graph

    # ---- backward-compatible access (same API as MetricCatalog) ----

    @property
    def entries(self) -> list[dict]:
        return [n for n in self._nodes if n.get("type") in ("kpi", "supporting_metric")]

    def __len__(self) -> int:
        return len(self.entries)

    def list(self, kind: str = None) -> list[dict]:
        entries = self.entries
        if kind:
            return [e for e in entries if e.get("type") == kind]
        return list(entries)

    def get(self, name_or_id: str) -> Optional[dict]:
        lower = name_or_id.strip().lower()
        for n in self._nodes:
            if n.get("id") == lower or n.get("name", "").lower() == lower:
                return n
        entries = self.entries
        try:
            idx = int(name_or_id) - 1
            if 0 <= idx < len(entries):
                return entries[idx]
        except ValueError:
            pass
        return None

    def get_by_priority(self, priority_name: str) -> list[dict]:
        lower = priority_name.strip().lower()
        return [n for n in self.entries if n.get("priority", "").lower() == lower]

    # ---- mutations ----

    def edit(self, name_or_id: str, field: str, value: str) -> bool:
        node = self.get(name_or_id)
        if not node:
            return False
        if field in ("description", "measurement", "metric"):
            node[field] = value
            node["source"] = "user-override"
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
                idx = self._nodes.index(old)
                self._nodes[idx] = replacement
                return True
        old["source"] = "llm-generated"
        return True

    # ---- formatting for prompts ----

    def format_for_prompt(self, name_or_id: str) -> str:
        node = self.get(name_or_id)
        if not node:
            return f"Metric '{name_or_id}' not found in catalog."
        inf = self._influence_names(node["id"])
        inf_str = f"\nInfluences: {', '.join(inf)}" if inf else ""
        return (
            f"--- {node['name']} ---\n"
            f"Kind: {node.get('type', '?')}\n"
            f"Source Column: {node.get('metric', '')}\n"
            f"Description: {node.get('description', '')}\n"
            f"Formula: {node.get('measurement', '')}{inf_str}\n"
        )

    # ---- graph traversal ----

    def traverse(self, node_id: str, relation: str = None, direction: str = "incoming") -> list[dict]:
        lower_id = node_id.strip().lower()
        results = []
        for edge in self._edges:
            if relation and edge.get("relation", "").lower() != relation.lower():
                continue
            src = edge.get("source", "").lower()
            tgt = edge.get("target", "").lower()
            if direction in ("incoming", "both") and tgt == lower_id:
                n = self._find_node(edge["source"])
                results.append({
                    "node": n,
                    "node_id": edge["source"],
                    "relation": edge.get("relation", ""),
                    "direction": "incoming",
                })
            if direction in ("outgoing", "both") and src == lower_id:
                n = self._find_node(edge["target"])
                results.append({
                    "node": n,
                    "node_id": edge["target"],
                    "relation": edge.get("relation", ""),
                    "direction": "outgoing",
                })
        return results

    def _find_node(self, node_id: str) -> Optional[dict]:
        for n in self._nodes:
            if n.get("id", "").lower() == node_id.lower():
                return n
        return None

    def _influence_names(self, node_id: str) -> list[str]:
        names = []
        for edge in self._edges:
            if edge.get("source", "").lower() == node_id.lower() and edge.get("relation") == "INFLUENCES":
                target = self._find_node(edge["target"])
                if target:
                    names.append(target.get("name", edge["target"]))
        return names

    # ---- display helpers ----

    def format_traverse(self, node_id: str, relation: str = None) -> str:
        results = self.traverse(node_id, relation, direction="both")
        if not results:
            return f"No connections found for '{node_id}'."
        lines = [f"Connections for '{node_id}':"]
        for r in results:
            name = r["node"].get("name", r["node_id"]) if r["node"] else r["node_id"]
            arrow = "<--" if r["direction"] == "incoming" else "-->"
            lines.append(f"  {name} {arrow} [{r['relation']}]")
        return "\n".join(lines)

    def format_summary(self) -> str:
        types = {}
        for n in self._nodes:
            t = n.get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        type_counts = ", ".join(f"{k}: {v}" for k, v in sorted(types.items()))
        rel_counts = {}
        for e in self._edges:
            r = e.get("relation", "unknown")
            rel_counts[r] = rel_counts.get(r, 0) + 1
        rel_str = ", ".join(f"{k}: {v}" for k, v in sorted(rel_counts.items()))
        return (
            f"  Nodes ({len(self._nodes)}): {type_counts}\n"
            f"  Edges ({len(self._edges)}): {rel_str}"
        )
