"""Regression suite: every expressible spec shape must validate AND execute AND (where
possible) match the independent L1 re-derivation.

These tests exist so a future DSL or engine change can never silently reintroduce the
two production failures it guards:
  1. "share of orders using '<value>'"   (spec LLM omitted it — engine had no safe shape)
  2. "mean(difference between A and B)"  (scalar agg over a derived column was rejected)
"""
import math

import pandas as pd
import pytest

from src.analyst import builder


def _df():
    """8 rows: 4 in the current period (Aug 2026), 4 in the prior (Jan-Feb 2026)."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime([
                "2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04",
                "2026-01-15", "2026-01-20", "2026-02-10", "2026-02-11",
            ]),
            "mode": ["Express Air", "Express Air", "Regular Air", "Regular Air",
                     "Express Air", "Regular Air", "Express Air", "Regular Air"],
            "agent": ["A", "A", "B", "B", "A", "B", "A", "B"],
            "value": [10, 20, 30, 40, 1, 2, 3, 4],
            "engage": pd.to_datetime([
                "2026-07-01", "2026-07-10", "2026-07-20", "2026-07-25",
                "2026-01-01", "2026-01-05", "2026-02-01", "2026-02-05",
            ]),
            "ship": pd.to_datetime([
                "2026-08-02", "2026-08-03", "2026-08-05", "2026-08-06",
                "2026-01-16", "2026-01-21", "2026-02-11", "2026-02-12",
            ]),
        }
    )


def _new_df():
    """Agent C first appears in Aug 2026; A and B first appeared in Jan/Feb 2026."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01", "2026-08-02", "2026-01-15", "2026-02-10"]),
            "agent": ["C", "A", "A", "B"],
        }
    )


def _period():
    return {
        "date_column": "date",
        "current_period": "Aug-2026",
        "prior_period": "Jan-Feb-2026",
        "current_start": "2026-08-01",
        "current_end": "2026-08-31",
        "prior_start": "2026-01-01",
        "prior_end": "2026-02-28",
        "definition_text": "current = rows in Aug 2026; prior = rows in Jan-Feb 2026",
    }


def _run(specs, df=None):
    df = _df() if df is None else df
    code = builder.build_metric_script(specs, _period())
    ok, out = builder.sandbox.execute_code(code, df)
    assert ok, out
    return builder._parse_compute_output(out)


def _assert_exec(value, expected=None):
    assert value is not None and math.isfinite(float(value))
    if expected is not None:
        assert abs(float(value) - expected) < 1e-9, f"{value} != {expected}"


COND = 'df["mode"] == "Express Air"'


class TestCountShare:
    """Regression: 'share of orders using <value>' must compute (was omitted)."""

    def test_bare_share_with_condition(self):
        spec = {"name": "Express Ship Adoption", "agg": "share", "condition": COND,
                "compare": "pct_change", "unit": "ratio"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 0.0)  # 2/4 == 2/4
        assert builder._recompute_value(_df(), _period(), spec) == pytest.approx(out["value"])

    def test_share_explicit_count_numerator_denominator(self):
        spec = {"name": "Express Ship Adoption", "agg": "share",
                "numerator": {"agg": "count", "condition": COND},
                "denominator": {"agg": "count"},
                "compare": "pct_change", "unit": "ratio"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 0.0)

    def test_share_with_value_column_keeps_value_semantics(self):
        spec = {"name": "Express Air Value Share", "agg": "share", "value_column": "value",
                "condition": COND, "compare": "level", "unit": "ratio"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 0.3)  # sum value where Express Air / total = 30/100


class TestScalarAggOverDerived:
    """Regression: 'mean(difference between A and B)' was rejected; must compute."""

    def test_mean_of_days_between_derived(self):
        spec = {"name": "Order-to-Ship Cycle", "agg": "mean",
                "prep": [{"op": "derive.days_between", "start": "engage", "end": "ship",
                          "as": "cycle_days"}],
                "value_column": "cycle_days", "compare": "pct_change", "unit": "days"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 0.75)  # mean 21 vs mean 12

    def test_median_of_days_between_derived(self):
        spec = {"name": "Median Cycle", "agg": "median",
                "prep": [{"op": "derive.days_between", "start": "engage", "end": "ship",
                          "as": "cycle_days"}],
                "value_column": "cycle_days", "compare": "pct_change", "unit": "days"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 0.6)  # median 20 vs median 12.5

    def test_group_step_null_group_by_whole_frame(self):
        # The exact shape the spec LLM emitted for cycle time — must not be rejected.
        spec = {"name": "Whole Frame Cycle", "agg": None,
                "prep": [{"op": "derive.days_between", "start": "engage", "end": "ship",
                          "as": "cycle_days"}],
                "steps": [{"op": "group", "group_by": None, "inner_agg": "mean",
                           "value": "cycle_days", "outer_agg": "mean"}],
                "compare": "level", "unit": "days"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 21.0)


class TestMedian:
    def test_median_agg(self):
        spec = {"name": "Median Value", "agg": "median", "value_column": "value",
                "compare": "pct_change", "unit": "currency"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 9.0)  # median 25 vs 2.5
        assert builder._recompute_value(_df(), _period(), spec) == pytest.approx(out["value"])

    def test_median_in_group_step(self):
        spec = {"name": "Median Per Agent", "agg": None,
                "steps": [{"op": "group", "group_by": "agent", "inner_agg": "median",
                           "value": "value", "outer_agg": "mean"}],
                "compare": "pct_change", "unit": "currency"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"])  # per-agent medians exist; value must be non-null


class TestSimpleAggs:
    @pytest.mark.parametrize("agg,expected", [
        ("count", 0.0),       # 2 vs 2 Express Air rows
        ("sum", 6.5),         # 30 vs 4 (Express Air values)
        ("mean", 6.5),        # 15 vs 2 (Express Air values)
        ("count_distinct", 0.0),  # {A} vs {A}
    ])
    def test_agg_with_condition(self, agg, expected):
        spec = {"name": "Metric", "agg": agg, "value_column": "value",
                "condition": COND, "compare": "pct_change", "unit": "ratio"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], expected)
        assert builder._recompute_value(_df(), _period(), spec) == pytest.approx(out["value"])

    def test_ratio_of_distinct_counts(self):
        spec = {"name": "Orders Per Customer", "agg": "ratio",
                "numerator": {"agg": "count_distinct", "value_column": "agent"},
                "denominator": {"agg": "count"},
                "compare": "pct_change", "unit": "ratio"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 0.0)  # 2/4 == 2/4

    def test_topk_share(self):
        spec = {"name": "Top Agent Share", "agg": "topk_share", "value_column": "value",
                "group_by": "agent", "k": 1, "compare": "level", "unit": "ratio"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 0.7)  # agent B holds 70/100


class TestComposedSteps:
    def test_group_avegarex(self):
        spec = {"name": "Avg Count Per Agent", "agg": None,
                "steps": [{"op": "group", "group_by": "agent", "inner_agg": "count",
                           "value": None, "outer_agg": "mean"}],
                "compare": "pct_change", "unit": "count"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec])[spec["name"]]
        _assert_exec(out["value"], 0.0)  # 2 and 2 per agent in both periods

    def test_new_step_first_time(self):
        spec = {"name": "New Agents", "agg": None,
                "steps": [{"op": "new", "value_column": "agent"}],
                "compare": "level", "unit": "count"}
        assert builder._validate_spec(spec, set(_df().columns))[0]
        out = _run([spec], df=_new_df())[spec["name"]]
        _assert_exec(out["value"], 1.0)  # only agent C is new


class TestPrecheckDoesNotBlockExpressibleShapes:
    def test_count_share_measurement_flows_to_llm(self):
        period = _period()
        reason, prim = builder._precheck_measurement(
            "Percentage change in share of orders using 'Express Air' compared to the prior period",
            period, df=_df())
        assert not reason, reason

    def test_derived_mean_measurement_flows_to_llm(self):
        period = _period()
        reason, prim = builder._precheck_measurement(
            "Percentage change in mean(difference between Ship Date and Order Date) compared to the prior period",
            period, df=_df())
        assert not reason, reason

    def test_delta_still_rejected_when_prior_is_empty(self):
        period = _period()
        period["prior_start"] = "2016-01-01"
        period["prior_end"] = "2016-01-31"
        reason, prim = builder._precheck_measurement(
            "Percentage change in share of orders using 'Express Air'", period, df=_df())
        assert reason and "prior" in reason
