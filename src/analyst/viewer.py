import json
import threading
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import markdown  # type: ignore[import-untyped]
import pandas as pd

HTML_PATH = Path(__file__).parent / "viewer.html"
MAX_CSV_ROWS = 1000


def _get_file_type(ext: str) -> str:
    ext = ext.lower()
    if ext == ".json":
        return "json"
    elif ext == ".csv":
        return "csv"
    elif ext == ".md":
        return "markdown"
    elif ext in (".txt", ".py", ".jsonl", ".log"):
        return "text"
    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"):
        return "image"
    else:
        return "text"


def _build_node(path: Path, base: Path) -> dict:
    rel = str(path.relative_to(base)).replace("\\", "/")
    if path.is_dir():
        children = []
        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith("."):
                continue
            children.append(_build_node(child, base))
        return {"name": path.name, "type": "directory", "path": rel, "children": children}
    else:
        return {
            "name": path.name,
            "type": "file",
            "path": rel,
            "fileType": _get_file_type(path.suffix),
        }


def _build_projects_tree(base: Path) -> list:
    if not base.exists():
        return []
    projects = []
    for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir() and not child.name.startswith("."):
            projects.append(_build_node(child, base))
    return projects


def _detect_view_type(rel_path: str) -> str | None:
    p = rel_path.replace("\\", "/")
    if "/analyses/" in p and p.endswith("/turns.jsonl"):
        return "analysis_turns"
    if p.endswith("/graphs/structural.json"):
        return "structural_kg"
    if p.endswith("/graphs/diagnostic.json"):
        return "diagnostic_kg"
    if p.endswith("/metadata/schema.json"):
        return "schema"
    if p.endswith("/metadata/priorities.json"):
        return "priorities"
    if p.endswith("/metadata/priority_values.json"):
        return "priority_values"
    if p.endswith("/metadata/briefing.json"):
        return "briefing"
    if p.endswith("/metadata/metric_catalog.json"):
        return "metric_catalog"
    if p.endswith("/metadata/knowledge_graph.json"):
        return "knowledge_graph"
    if p.endswith("/metadata/reasoning_framework.json"):
        return "reasoning_framework"
    if p.endswith("/metadata/custom_instructions.json"):
        return "custom_instructions"
    if p.endswith("/analyst.json"):
        return "project_meta"
    return None


def _md_to_html(text: str) -> str:
    try:
        return markdown.markdown(text, extensions=["extra"])
    except Exception:
        return f"<pre>{text}</pre>"


def _preprocess_markdown(data: "dict[Any, Any] | Sequence[Any]", view_type: str):
    if view_type == "analysis_turns" and isinstance(data, list):
        for turn in data:
            if "summary" in turn and isinstance(turn["summary"], str):
                turn["summary_html"] = _md_to_html(turn["summary"])
    elif view_type == "briefing":
        if isinstance(data, dict):
            insights = data.get("priority_insights", [])
            for item in insights:
                if "insight" in item and isinstance(item["insight"], str):
                    item["insight_html"] = _md_to_html(item["insight"])
    elif view_type == "priorities" and isinstance(data, list):
        for pri in data:
            if "description" in pri and isinstance(pri["description"], str):
                pri["description_html"] = _md_to_html(pri["description"])
            if "analysis_summary" in pri and isinstance(pri["analysis_summary"], str):
                pri["analysis_summary_html"] = _md_to_html(pri["analysis_summary"])


class _Handler(BaseHTTPRequestHandler):
    projects_base: Path | None = None

    def _json_response(self, data, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode("utf-8"))

    def _html_response(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if HTML_PATH.exists():
            html = HTML_PATH.read_text(encoding="utf-8")
            self.wfile.write(html.encode("utf-8"))
        else:
            self.wfile.write(b"<h1>viewer.html not found</h1>")

    def _safe_path(self, rel_path: str) -> Path | None:
        norm = rel_path.replace("\\", "/").lstrip("/")
        assert self.projects_base is not None, "projects_base must be set before serving"
        requested = (self.projects_base / norm).resolve()
        base_resolved = self.projects_base.resolve()
        try:
            requested.relative_to(base_resolved)
        except ValueError:
            return None
        if not requested.exists():
            return None
        return requested

    def _handle_file_content(self, requested: Path, rel_path: str) -> dict:
        ext = requested.suffix.lower()

        if ext == ".json" or ext == ".jsonl":
            return self._handle_json_content(requested, rel_path)

        elif ext == ".csv":
            try:
                df = pd.read_csv(requested, nrows=MAX_CSV_ROWS)
            except Exception:
                return {"path": rel_path, "type": "text", "content": requested.read_text(encoding="utf-8", errors="replace")}
            total_rows = len(df) if len(df) < MAX_CSV_ROWS else sum(1 for _ in open(requested, encoding="utf-8")) - 1
            return {
                "path": rel_path,
                "type": "csv",
                "content": {
                    "columns": list(df.columns),
                    "rows": df.fillna("").values.tolist(),
                    "rowCount": total_rows,
                },
            }

        elif ext == ".md":
            text = requested.read_text(encoding="utf-8")
            try:
                html = _md_to_html(text)
            except Exception:
                html = f"<pre>{text}</pre>"
            return {"path": rel_path, "type": "markdown", "content": html}

        else:
            try:
                text = requested.read_text(encoding="utf-8")
                return {"path": rel_path, "type": "text", "content": text}
            except UnicodeDecodeError:
                return {"path": rel_path, "type": "binary", "content": None}
            except Exception:
                return {"path": rel_path, "type": "text", "content": ""}

    def _handle_json_content(self, requested: Path, rel_path: str) -> dict:
        view_type = _detect_view_type(rel_path)

        if view_type == "analysis_turns":
            try:
                turns = []
                for line in requested.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        turns.append(json.loads(line))
            except Exception:
                return {"path": rel_path, "type": "text", "content": requested.read_text(encoding="utf-8", errors="replace")}
            result = {"path": rel_path, "type": "json", "viewType": view_type, "content": turns}
            _preprocess_markdown(result["content"], view_type)
            return result

        try:
            content = json.loads(requested.read_text(encoding="utf-8"))
        except Exception:
            raw = requested.read_text(encoding="utf-8", errors="replace")
            return {"path": rel_path, "type": "text", "content": raw}

        result = {"path": rel_path, "type": "json", "content": content}
        if view_type:
            result["viewType"] = view_type
            _preprocess_markdown(content, view_type)
        return result

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._html_response()

        elif path == "/api/tree":
            assert self.projects_base is not None
            tree = _build_projects_tree(self.projects_base)
            self._json_response({"projects": tree})

        elif path == "/api/file":
            rel = qs.get("path", [None])[0]
            if not rel:
                self._json_response({"error": "Missing path parameter"}, 400)
                return
            safe = self._safe_path(rel)
            if safe is None:
                self._json_response({"error": "File not found or access denied"}, 404)
                return
            result = self._handle_file_content(safe, rel)
            self._json_response(result)

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def log_message(self, fmt, *args):
        pass


def start_background(projects_base, port: int = 8081) -> HTTPServer:
    _Handler.projects_base = Path(projects_base)
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
