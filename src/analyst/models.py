"""Typed descriptions of the domain shapes shared across analyst modules.

The project persists plain dicts (JSON) — on-disk formats are NOT changed here.
These ``TypedDict``/``dataclass`` types document the contracts for mypy/docs and
provide the single, unified way to walk a priority's metrics regardless of shape.

Key helpers
-----------
``iter_priority_metrics`` yields ``(kind, metric)`` for every KPI and operational
metric in a priority. It collapses the three priority shapes:
  1. ``kpis`` with nested ``operational_metrics``
  2. ``executive_questions`` (objects) with nested ``kpis`` / ``supporting_metrics``
  3. legacy flat ``kpis`` + ``supporting_metrics``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from src.analyst.constants import (
    KIND_KPI,
    KIND_OPERATIONAL,
    PRIORITY_EXECUTIVE_QUESTIONS,
    PRIORITY_KPIS,
    PRIORITY_OPERATIONAL_METRICS,
    PRIORITY_SUPPORTING_METRICS,
)

KIND_METRIC_LITERALS = (KIND_KPI, KIND_OPERATIONAL)


class MetricSpec(TypedDict, total=False):
    """A metric's computation definition (produced by the spec LLM, validated & run)."""

    name: str
    agg: str
    compare: str
    value_column: str | None
    unit: str
    kind: str
    steps: list[dict]
    prep: list[dict]
    input_ref: str
    numerator: dict
    denominator: dict
    condition: str | None
    group_by: str | None
    k: int | float | None
    code: str


class ValueRecord(TypedDict, total=False):
    """One metric's computed value record (persisted in ``priority_values.json``)."""

    filters: list
    value: int | float | None
    unit: str
    basis: str
    period: str | None
    measurement: str
    spec: dict | None
    verified: bool
    status: str
    reason: str
    reason_display: str
    missing_primitive: str
    source: str
    verification: dict


class PeriodRecord(TypedDict, total=False):
    """The canonical current-vs-prior time period for a compute run."""

    date_column: str | None
    period_unit: str | None
    current_period: str | None
    prior_period: str | None
    current_start: str | None
    current_end: str | None
    prior_start: str | None
    prior_end: str | None
    definition_text: str


class ExecutiveQuestion(TypedDict, total=False):
    question: str
    kpis: list[dict]
    supporting_metrics: list[dict]


class Kpi(TypedDict, total=False):
    name: str
    metric: str
    description: str
    measurement: str
    analytical_lenses: list[str]
    operational_metrics: list[dict]


class Priority(TypedDict, total=False):
    name: str
    description: str
    executive_questions: list[ExecutiveQuestion | str]
    kpis: list[Kpi]
    supporting_metrics: list[dict]


@dataclass(frozen=True)
class Metric:
    """Normalized view of a KPI or operational metric inside a priority."""

    name: str
    kind: str
    metric: str = ""  # source column
    description: str = ""
    measurement: str = ""
    analytical_lenses: list[str] = field(default_factory=list)
    influences: list[str] = field(default_factory=list)
    operational_metrics: list[Metric] = field(default_factory=list)
    executive_question: str = ""


def iter_priority_metrics(pri: dict):
    """Yield ``(kind, metric_dict)`` for every KPI and operational metric.

    Honors the three priority shapes (see module docstring). ``kind`` is one of
    ``KIND_KPI`` / ``KIND_OPERATIONAL``. Used by compute, fingerprints, briefs,
    and graph building so the shape decision lives in exactly one place.
    """
    kpis = pri.get(PRIORITY_KPIS, [])
    if kpis:
        for k in kpis:
            yield KIND_KPI, k
            for op in k.get(PRIORITY_OPERATIONAL_METRICS, []):
                yield KIND_OPERATIONAL, op
        return
    eqs = pri.get(PRIORITY_EXECUTIVE_QUESTIONS, [])
    if eqs and isinstance(eqs[0], dict):
        for eq in eqs:
            for k in eq.get(PRIORITY_KPIS, []):
                yield KIND_KPI, k
            for s in eq.get(PRIORITY_SUPPORTING_METRICS, []):
                yield KIND_OPERATIONAL, s
        return
    for k in pri.get(PRIORITY_KPIS, []):
        yield KIND_KPI, k
    for s in pri.get(PRIORITY_SUPPORTING_METRICS, []):
        yield KIND_OPERATIONAL, s


def collect_supporting_metrics(pri: dict) -> list[dict]:
    """All operational/supporting metrics of a priority, in order."""
    return [m for kind, m in iter_priority_metrics(pri) if kind == KIND_OPERATIONAL]
