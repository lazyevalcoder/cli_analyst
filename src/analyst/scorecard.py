"""Build the read-only scorecard payload consumed by the end-user scorecard page.

This is a *pure connector* between what the pipeline already persists
(``priority_values.json`` + ``priorities.json``) and what the viewer's
``/api/scorecard`` endpoint returns. It:

- groups computed values into sections (one per priority, in file order),
- derives the matrix columns (Overall + the priority's breakdown members),
- maps each metric's overall value and its per-member breakdown ``delta`` into
  ready-for-display primitives (no HTML, no unit string building).

It exists so the frontend stays a thin renderer and the shape is unit-testable
in Python without a browser. No values are computed or mutated here.
"""

from __future__ import annotations

from src.analyst.constants import (
    BREAKDOWN_AT,
    BREAKDOWN_COLUMN,
    BREAKDOWN_DELTA,
    BREAKDOWN_MEMBERS,
    PRIORITY_NAME,
    RESULT_BREAKDOWN_DIMENSIONS,
    RESULT_BREAKDOWNS,
    RESULT_ENGINE_VERSION,
    RESULT_GENERATED_AT,
    RESULT_PERIOD_DEFINITION,
    RESULT_PRIORITIES,
    RESULT_VALUES,
)
from src.analyst.models import iter_priority_metrics

PRIORITY = "priority"
DESCRIPTION = "description"
DIMENSION = "dimension"
COLUMNS = "columns"
SECTIONS = "sections"
ROWS = "rows"
NAME = "name"
KIND = "kind"
UNIT = "unit"
OVERALL = "overall"
CELLS = "cells"
STATUS = "status"
VALUE = "value"
BASIS = "basis"
VERIFIED = "verified"
REASON = "reason"

OVERALL_LABEL = "Overall"


def build_scorecard_payload(project: str, priority_values: dict, priorities: list) -> dict:
    """Assemble the scorecard payload from persisted priority values + definitions.

    ``priority_values`` is the decoded ``metadata/priority_values.json`` envelope;
    ``priorities`` the decoded ``metadata/priorities.json`` list. Sections mirror
    the priorities list order; within a section rows follow KPI-then-operational
    metric order (see ``models.iter_priority_metrics``).
    """
    pri_defs = {str(p.get("name", "")): p for p in priorities if isinstance(p, dict)}
    sections = []
    for pri_rec in (priority_values.get(RESULT_PRIORITIES) or {}).values():
        if not isinstance(pri_rec, dict):
            continue
        pname = str(pri_rec.get(PRIORITY_NAME, pri_rec.get("priority_ref", "")))
        section = _build_section(pname, pri_rec, pri_defs.get(pname, {}))
        if section[ROWS]:
            sections.append(section)

    return {
        "project": project,
        "period_definition": priority_values.get(RESULT_PERIOD_DEFINITION, ""),
        "generated_at": priority_values.get(RESULT_GENERATED_AT, ""),
        "engine_version": priority_values.get(RESULT_ENGINE_VERSION, ""),
        COLUMNS: [OVERALL_LABEL],
        SECTIONS: sections,
    }


def _build_section(pname: str, rec: dict, pri_def: dict) -> dict:
    values = rec.get(RESULT_VALUES) or {}
    dims = rec.get(RESULT_BREAKDOWN_DIMENSIONS) or []
    dim = dims[0] if isinstance(dims, list) and dims and isinstance(dims[0], dict) else {}
    dcol = str(dim.get(BREAKDOWN_COLUMN, "")) if dim else ""
    members = [str(m) for m in (dim.get(BREAKDOWN_MEMBERS) or [])] if dim else []
    breakdowns = rec.get(RESULT_BREAKDOWNS) or {}
    col_breakdowns = breakdowns.get(dcol, {}) if dcol else {}

    rows: list[dict] = []
    for kind, metric in iter_priority_metrics(pri_def):
        name = str(metric.get("name", ""))
        if not name:
            continue
        recv = values.get(name) if isinstance(values, dict) else None
        row: dict = {
            NAME: name,
            KIND: "kpi" if str(kind).lower() == "kpi" else "op",
            UNIT: str(recv.get("unit", "")) if recv else "",
            OVERALL: _parse_record(recv),
        }
        cells = col_breakdowns.get(name) if isinstance(col_breakdowns, dict) else None
        if cells:
            row[CELLS] = _parse_breakdown_cells(cells)
        rows.append(row)

    return {
        PRIORITY: pname,
        DESCRIPTION: str(pri_def.get("description", "")),
        DIMENSION: dcol,
        COLUMNS: [OVERALL_LABEL, *members],
        ROWS: rows,
    }


def _parse_record(rec) -> dict | None:
    """One overall value cell (None when there is no persisted record)."""
    if not isinstance(rec, dict):
        return None
    return {
        STATUS: str(rec.get("status", "")),
        VALUE: rec.get("value"),
        UNIT: str(rec.get("unit", "")),
        BASIS: str(rec.get("basis", "")),
        VERIFIED: bool(rec.get("verified", False)),
        REASON: str(rec.get("reason_display") or rec.get("reason", "")),
    }


def _parse_breakdown_cells(cells) -> dict:
    """Map ``[{member, delta, status, ...}]`` to ``{member: cell}`` for the UI."""
    out: dict = {}
    for c in cells:
        if not isinstance(c, dict):
            continue
        member = str(c.get(BREAKDOWN_AT, ""))
        if not member:
            continue
        out[member] = {
            STATUS: str(c.get("status", "")),
            VALUE: c.get(BREAKDOWN_DELTA),
            UNIT: str(c.get("unit", "")),
            BASIS: str(c.get("basis", "")),
            VERIFIED: bool(c.get("verified", False)),
            REASON: str(c.get("reason_display") or c.get("reason", "")),
        }
    return out
