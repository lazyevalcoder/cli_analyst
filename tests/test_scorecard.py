"""Scorecard payload builder tests.

Verifies the pure connector between persisted priority values/definitions and the
display payload the viewer's ``/api/scorecard`` endpoint returns.
"""

import json

from src.analyst.scorecard import (
    CELLS,
    COLUMNS,
    DIMENSION,
    EXECUTIVE_QUESTIONS,
    KIND,
    MEASUREMENT,
    NAME,
    OVERALL,
    PRIORITY,
    REASON,
    ROWS,
    SECTIONS,
    STATUS,
    UNIT,
    VALUE,
    build_scorecard_payload,
)
from src.analyst.viewer import _json_safe

# ---------------------------------------------------------------------------
# Fixtures (mirror the on-disk shapes of priority_values.json / priorities.json)
# ---------------------------------------------------------------------------


def _priority_def(name, description, kpis, supporting=None):
    pri = {
        "name": name,
        "description": description,
        "executive_questions": ["Q1?"],
        "kpis": kpis,
        "supporting_metrics": supporting or [],
    }
    return pri


def _metric(name, measurement):
    return {"name": name, "metric": "Sales", "measurement": measurement}


def _value_record(status="computed", value=None, unit="percent", basis="", reason=""):
    rec = {
        "status": status,
        "value": value,
        "unit": unit,
        "basis": basis,
        "verified": status == "computed",
        "reason": reason,
    }
    return rec


def _breakdown_cell(member, delta, status="computed", unit="percent", basis="", reason=""):
    return {
        "member": member,
        "current": 100.0,
        "prior": 90.0,
        "delta": delta,
        "unit": unit,
        "basis": basis,
        "status": status,
        "verified": status == "computed",
        "reason": reason,
        "reason_display": reason,
    }


def _sample_project():
    priorities = [
        _priority_def(
            "P1",
            "Top line.",
            kpis=[
                {
                    "name": "Revenue Growth",
                    "metric": "Sales",
                    "measurement": "pct change in sum(Sales)",
                    "operational_metrics": [_metric("Units Sold", "sum(Quantity)")],
                },
            ],
        ),
        _priority_def("P2", "Margins.", kpis=[_metric("GM%", "sum(Profit)/sum(Sales)")]),
    ]

    priority_values = {
        "generated_at": "2026-08-02T00:00:00",
        "engine_version": "engine-v3-2026-08-02-breakdowns",
        "period_definition": "current = Q4-2013; prior = Q3-2013",
        "priorities": {
            "P1": {
                "priority_ref": "P1",
                "values": {
                    "Revenue Growth": _value_record(value=0.487, basis="current 1.07e+06 vs prior 7.23e+05"),
                    "Units Sold": _value_record(value=0.1, unit="ratio"),
                },
                "breakdown_dimensions": [
                    {
                        "column": "Region",
                        "rationale": "regions",
                        "members": ["East", "West"],
                    }
                ],
                "breakdowns": {
                    "Region": {
                        "Revenue Growth": [
                            _breakdown_cell("East", 0.379, basis="current 1e+05 vs prior 8e+04"),
                            _breakdown_cell("West", None, status="not_computable", reason="no baseline"),
                        ],
                    }
                },
            },
            "P2": {
                "priority_ref": "P2",
                "values": {
                    "GM%": _value_record(value=0.05, unit="ratio"),
                },
                "breakdown_dimensions": [],
                "breakdowns": {},
            },
        },
    }
    return priorities, priority_values


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildScorecardPayload:
    def test_header_fields(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        assert payload["project"] == "Acme"
        assert payload["period_definition"] == "current = Q4-2013; prior = Q3-2013"
        assert payload["generated_at"] == "2026-08-02T00:00:00"
        assert payload[COLUMNS] == ["Overall"]

    def test_sections_ordered_and_filtered(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        names = [s[PRIORITY] for s in payload[SECTIONS]]
        assert names == ["P1", "P2"]
        assert payload[SECTIONS][0][DIMENSION] == "Region"

    def test_section_columns_overall_then_members(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        section = payload[SECTIONS][0]
        assert section[COLUMNS] == ["Overall", "East", "West"]

    def test_rows_follow_definition_order_kind(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        rows = payload[SECTIONS][0][ROWS]
        assert [(r[NAME], r[KIND]) for r in rows] == [("Revenue Growth", "kpi"), ("Units Sold", "op")]

    def test_row_carries_measurement_definition(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        rows = payload[SECTIONS][0][ROWS]
        assert rows[0][MEASUREMENT] == "pct change in sum(Sales)"
        assert rows[1][MEASUREMENT] == "sum(Quantity)"

    def test_row_measurement_defaults_to_empty(self):
        priorities, pv = _sample_project()
        priorities[0]["kpis"][0].pop("measurement")
        payload = build_scorecard_payload("Acme", pv, priorities)
        row = payload[SECTIONS][0][ROWS][0]
        assert row[MEASUREMENT] == ""

    def test_section_exposes_executive_questions(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        section = payload[SECTIONS][0]
        assert section[EXECUTIVE_QUESTIONS] == ["Q1?"]

    def test_section_executive_questions_default_to_empty(self):
        priorities, pv = _sample_project()
        priorities[0].pop("executive_questions")
        payload = build_scorecard_payload("Acme", pv, priorities)
        assert payload[SECTIONS][0][EXECUTIVE_QUESTIONS] == []

    def test_overall_cell_parsed(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        row = payload[SECTIONS][0][ROWS][0]
        assert row[OVERALL][STATUS] == "computed"
        assert row[OVERALL][VALUE] == 0.487
        assert row[OVERALL]["basis"] == "current 1.07e+06 vs prior 7.23e+05"
        assert row[OVERALL]["verified"] is True
        assert row[UNIT] == "percent"

    def test_breakdown_cells_keyed_by_member(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        row = payload[SECTIONS][0][ROWS][0]
        cells = row[CELLS]
        assert cells["East"][VALUE] == 0.379
        assert cells["East"][STATUS] == "computed"
        assert cells["West"][VALUE] is None
        assert cells["West"][STATUS] == "not_computable"
        assert cells["West"][REASON] == "no baseline"

    def test_section_without_breakdown_has_no_cells(self):
        priorities, pv = _sample_project()
        payload = build_scorecard_payload("Acme", pv, priorities)
        row = payload[SECTIONS][1][ROWS][0]
        assert row[OVERALL][VALUE] == 0.05
        assert row.get(CELLS) in (None, {})

    def test_empty_priorities(self):
        payload = build_scorecard_payload("Acme", {"priorities": {}}, [])
        assert payload[SECTIONS] == []

    def test_non_dict_priority_records_skipped(self):
        payload = build_scorecard_payload("Acme", {"priorities": {"P1": "junk"}}, [])
        assert payload[SECTIONS] == []

    def test_nan_values_coerced_to_none_in_payload(self):
        """NaN/inf values (e.g. a 0/0 delta) must serialize as null, not the
        non-standard `NaN`/`Infinity` JSON tokens strict parsers reject."""
        priorities, pv = _sample_project()
        pv["priorities"]["P1"]["values"]["Revenue Growth"]["value"] = float("nan")
        payload = build_scorecard_payload("Acme", pv, priorities)
        row = payload[SECTIONS][0][ROWS][0]
        assert row[OVERALL][VALUE] is None
        text = json.dumps(payload)
        assert "NaN" not in text and "Infinity" not in text
        json.loads(text)  # round-trips as strictly valid JSON

    def test_viewer_json_safe_recursively_nulls_nonfinite(self):
        """The serialization boundary turns any NaN/inf float into null, wherever it
        sits in the payload, so the browser's JSON.parse never sees a NaN token."""
        import math

        data = {
            "rows": [{"value": float("nan"), "ok": True}],
            "cells": {"a": float("inf"), "b": -float("inf"), "c": 1.5},
            "nested": {"x": [float("nan"), 2]},
        }
        safe = _json_safe(data)
        text = json.dumps(safe)
        assert "NaN" not in text and "Infinity" not in text
        assert json.loads(text)["rows"][0]["value"] is None
        assert safe["cells"]["a"] is None and safe["cells"]["b"] is None
        assert safe["cells"]["c"] == 1.5
        assert safe["nested"]["x"] == [None, 2]
        assert math.isfinite(1.5)  # finite floats untouched
