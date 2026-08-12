import pandas as pd

from src.analyst import builder, llm, sandbox


def _sample_df():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-15", "2026-02-10", "2026-08-01", "2026-08-02"]),
            "value": [1, 2, 3, 4],
        }
    )


def _sample_pri():
    return {
        "name": "Growth",
        "description": "Test priority",
        "executive_questions": ["Are we growing?", "Where is growth concentrated?"],
        "kpis": [
            {
                "name": "Growth",
                "metric": "date",
                "measurement": "current count vs prior count",
                "operational_metrics": [{"name": "Deal Count", "metric": "date", "measurement": "count of rows in current period"}],
            }
        ],
    }


def _period():
    return {
        "date_column": "date",
        "period_unit": "month",
        "current_period": "Aug-2026",
        "prior_period": "Jan-Feb-2026",
        "current_start": "2026-08-01",
        "current_end": "2026-08-31",
        "prior_start": "2026-01-01",
        "prior_end": "2026-02-28",
        "definition_text": "current = rows in Aug 2026; prior = rows in Jan-Feb 2026",
    }


def _group_df():
    """8 rows across two agents and two periods (Aug 2026 current, Jan-Feb 2026 prior)."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-08-01",
                    "2026-08-02",
                    "2026-08-03",
                    "2026-08-04",
                    "2026-01-15",
                    "2026-01-20",
                    "2026-02-10",
                    "2026-02-11",
                ]
            ),
            "agent": ["A", "A", "B", "B", "A", "B", "A", "B"],
            "value": [10, 20, 30, 40, 1, 2, 3, 4],
        }
    )


def _derive_df():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-03"]),
            "engage": pd.to_datetime(["2026-07-01", "2026-07-10", "2026-07-20"]),
            "close": pd.to_datetime(["2026-08-01", "2026-08-01", "2026-08-03"]),
            "qty": [2, 3, 5],
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


def _specs():
    return [
        {
            "name": "Growth",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "pct_change",
            "unit": "ratio",
        },
        {
            "name": "Deal Count",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "count",
        },
    ]


def _all_aggs_specs():
    return [
        {
            "name": "CountLvl",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "count",
        },
        {
            "name": "CountPct",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "pct_change",
            "unit": "ratio",
        },
        {
            "name": "CountPP",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "pp_change",
            "unit": "pp",
        },
        {
            "name": "CountRate",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "rate_ratio",
            "unit": "ratio",
        },
        {
            "name": "SumLvl",
            "agg": "sum",
            "value_column": "value",
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "currency",
        },
        {
            "name": "MeanLvl",
            "agg": "mean",
            "value_column": "value",
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "currency",
        },
        {
            "name": "StdLvl",
            "agg": "std",
            "value_column": "value",
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "currency",
        },
        {
            "name": "RatioLvl",
            "agg": "ratio",
            "numerator": {"agg": "sum", "value_column": "value", "condition": None},
            "denominator": {"agg": "count", "value_column": None, "condition": None},
            "value_column": None,
            "condition": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "currency",
        },
        {
            "name": "ShareLvl",
            "agg": "share",
            "numerator": {"agg": "sum", "value_column": "value", "condition": None},
            "denominator": {"agg": "sum", "value_column": "value", "condition": None},
            "value_column": None,
            "condition": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "ratio",
        },
        {
            "name": "TopK",
            "agg": "topk_share",
            "value_column": "value",
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": "date",
            "k": 1,
            "compare": "level",
            "unit": "ratio",
        },
    ]


class TestFingerprints:
    def test_priority_fingerprint_stable(self):
        assert builder.priority_fingerprint(_sample_pri()) == builder.priority_fingerprint(_sample_pri())

    def test_priority_fingerprint_changes_on_measurement_edit(self):
        pri = _sample_pri()
        pri["kpis"][0]["measurement"] = "changed formula"
        assert builder.priority_fingerprint(pri) != builder.priority_fingerprint(_sample_pri())

    def test_data_fingerprint_stable_for_same_df(self):
        assert builder.data_fingerprint(_sample_df()) == builder.data_fingerprint(_sample_df())

    def test_data_fingerprint_changes_on_reload(self):
        df = _sample_df()
        df2 = pd.concat([df, pd.DataFrame({"date": pd.to_datetime(["2026-09-01"]), "value": [9]})], ignore_index=True)
        assert builder.data_fingerprint(df) != builder.data_fingerprint(df2)


class TestHelpers:
    def test_sandbox_function_sees_module_vars(self):
        df = _sample_df()
        code = """
total = len(df)
def double(x):
    return x * 2
print(total, double(3))
"""
        ok, out = sandbox.execute_code(code, df)
        assert ok
        assert "4 6" in out

    def test_parse_compute_output(self):
        out = 'some log\n{"Growth": {"value": 0.5, "unit": "ratio", "basis": "a vs b"}}\ntrailing'
        parsed = builder._parse_compute_output(out)
        assert parsed["Growth"]["value"] == 0.5

    def test_parse_compute_output_garbage(self):
        assert builder._parse_compute_output("(no output)") == {}


class TestSpecs:
    def test_parse_specs_list(self):
        raw = [{"name": "A", "agg": "count"}, {"name": "B", "agg": "sum"}]
        assert [s["name"] for s in builder._parse_specs(raw)] == ["A", "B"]

    def test_parse_specs_wrapped(self):
        assert builder._parse_specs({"specs": [{"name": "A"}]})[0]["name"] == "A"

    def test_parse_specs_mapping(self):
        assert builder._parse_specs({"A": {"agg": "count"}})[0]["name"] == "A"

    def test_parse_specs_garbage(self):
        assert builder._parse_specs("not a dict") == []
        assert builder._parse_specs({"specs": "x"}) == []

    def test_validate_ok(self):
        ok, msg = builder._validate_spec(_specs()[0], {"date"})
        assert ok, msg

    def test_validate_unknown_agg(self):
        spec = dict(_specs()[0], agg="bogus")
        ok, msg = builder._validate_spec(spec, {"date"})
        assert not ok and "agg" in msg

    def test_validate_unknown_compare(self):
        spec = dict(_specs()[0], compare="yo")
        ok, msg = builder._validate_spec(spec, {"date"})
        assert not ok and "compare" in msg

    def test_validate_bad_column(self):
        spec = {"name": "X", "agg": "sum", "value_column": "nope", "compare": "level", "unit": "count"}
        ok, msg = builder._validate_spec(spec, {"date"})
        assert not ok and "not in schema" in msg

    def test_validate_blocked_condition(self):
        spec = {"name": "X", "agg": "count", "condition": "import os", "compare": "level", "unit": "count"}
        ok, msg = builder._validate_spec(spec, {"date"})
        assert not ok

    def test_validate_bad_condition_syntax(self):
        spec = {"name": "X", "agg": "count", "condition": "df['date'] ===", "compare": "level", "unit": "count"}
        ok, msg = builder._validate_spec(spec, {"date"})
        assert not ok

    def test_validate_topk_requires_k(self):
        spec = {
            "name": "X",
            "agg": "topk_share",
            "value_column": "value",
            "group_by": "date",
            "k": None,
            "compare": "level",
            "unit": "ratio",
        }
        ok, msg = builder._validate_spec(spec, {"date", "value"})
        assert not ok

    def test_validate_group_missing_outer_agg_defaults_to_mean(self):
        spec = {
            "name": "X",
            "steps": [{"op": "group", "group_by": "agent", "inner_agg": "count", "value": None}],
            "compare": "level",
            "unit": "count",
        }
        ok, msg = builder._validate_spec(spec, {"agent", "value"})
        assert ok, msg
        assert spec["steps"][0]["outer_agg"] == "mean"

    def test_validate_group_bad_outer_agg_still_rejected(self):
        spec = {
            "name": "X",
            "steps": [{"op": "group", "group_by": "agent", "inner_agg": "count", "value": None, "outer_agg": "bogus"}],
            "compare": "level",
            "unit": "count",
        }
        ok, msg = builder._validate_spec(spec, {"agent", "value"})
        assert not ok and "outer_agg" in msg


class TestTemplate:
    def test_all_aggs_and_compares(self):
        code = builder.build_metric_script(_all_aggs_specs(), _period())
        ok, out = sandbox.execute_code(code, _sample_df())
        assert ok, out
        parsed = builder._parse_compute_output(out)
        # current period (Aug 2026) has 2 rows: value 3, 4. prior (Jan-Feb 2026) has 2 rows: 1, 2.
        assert parsed["CountLvl"]["value"] == 2
        assert abs(parsed["CountPct"]["value"]) < 1e-9  # (2-2)/2
        assert abs(parsed["CountPP"]["value"]) < 1e-9  # 2-2 pp
        assert abs(parsed["CountRate"]["value"] - 1.0) < 1e-9
        assert parsed["SumLvl"]["value"] == 7
        assert abs(parsed["MeanLvl"]["value"] - 3.5) < 1e-9
        assert parsed["RatioLvl"]["value"] == 3.5  # 7 / 2
        assert abs(parsed["ShareLvl"]["value"] - 1.0) < 1e-9  # 7/7
        assert abs(parsed["TopK"]["value"] - 4 / 7) < 1e-9  # top-1 share by date

    def test_template_with_condition(self):
        specs = [
            {
                "name": "Won Count",
                "agg": "count",
                "value_column": None,
                "condition": "df['value'] > 2",
                "compare": "level",
                "unit": "count",
            }
        ]
        code = builder.build_metric_script(specs, _period())
        ok, out = sandbox.execute_code(code, _sample_df())
        assert ok, out
        assert builder._parse_compute_output(out)["Won Count"]["value"] == 2

    def test_bad_metric_does_not_kill_others(self):
        specs = [
            {"name": "Good", "agg": "count", "compare": "level", "unit": "count"},
            {"name": "Bad", "agg": "sum", "value_column": "missing_col", "compare": "level", "unit": "count"},
        ]
        code = builder.build_metric_script(specs, _period())
        ok, out = sandbox.execute_code(code, _sample_df())
        assert ok
        parsed = builder._parse_compute_output(out)
        assert "Good" in parsed
        assert "Bad" not in parsed

    def test_pct_change_zero_prior_null_reason(self):
        spec = {
            "name": "Growth",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "pct_change",
            "unit": "count",
        }
        period = dict(_period(), prior_start="2016-01-01", prior_end="2016-01-31")
        code = builder.build_metric_script([spec], period)
        ok, out = sandbox.execute_code(code, _sample_df())
        assert ok, out
        rec = builder._parse_compute_output(out)["Growth"]
        assert rec["value"] is None
        assert rec["null_reason"] == "no prior-period baseline (prior value is 0)"

    def test_level_null_has_no_null_reason(self):
        spec = {
            "name": "Growth",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "count",
        }
        code = builder.build_metric_script([spec], _period())
        ok, out = sandbox.execute_code(code, _sample_df())
        assert ok, out
        rec = builder._parse_compute_output(out)["Growth"]
        assert rec["value"] == 2
        assert rec["null_reason"] is None


class TestPeriodBounds:
    def test_deterministic_quarter_fallback(self):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            b = builder._period_bounds("quarter", pd.Timestamp("2026-08-02"))
        assert b is not None
        # most recent complete quarter ending on/before 2026-08-02 = Q2 2026 (Apr-Jun)
        assert b["current_start"] == "2026-04-01"
        assert b["current_end"] == "2026-06-30"
        assert b["prior_start"] == "2026-01-01"
        assert b["prior_end"] == "2026-03-31"

    def test_deterministic_month_fallback(self):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            b = builder._period_bounds("month", pd.Timestamp("2026-08-02"))
        assert b["current_start"] == "2026-07-01"
        assert b["current_end"] == "2026-07-31"

    def test_valid_bounds(self):
        assert builder._valid_bounds(_period())
        assert not builder._valid_bounds({"current_start": None, "current_end": None, "prior_start": None, "prior_end": None})
        assert not builder._valid_bounds(
            {"current_start": "2026-08-31", "current_end": "2026-08-01", "prior_start": "2026-07-01", "prior_end": "2026-07-31"}
        )


class TestResolvePeriod:
    def test_placeholder_substituted_into_definition(self, monkeypatch):
        import warnings

        df = _sample_df()
        monkeypatch.setattr(
            builder.llm,
            "ask_json",
            lambda *a, **k: {
                "date_column": "date",
                "period_unit": "quarter",
                "current_period": "Q3-2026",
                "prior_period": "Q2-2026",
                "current_start": "2026-07-01",
                "current_end": "2026-09-30",
                "prior_start": "2026-04-01",
                "prior_end": "2026-06-30",
                "definition_text": "current = rows where {date_column} falls in the most recent complete calendar quarter",
            },
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            period = builder.resolve_period(df, "schema")
        assert period["date_column"] == "date"
        assert "{date_column}" not in period["definition_text"]
        assert "current = rows where date falls in the most recent complete calendar quarter" == period["definition_text"]
        assert period["current_start"] == "2026-07-01"

    def test_missing_bounds_use_deterministic_fallback(self, monkeypatch):
        import warnings

        df = _sample_df()
        monkeypatch.setattr(
            builder.llm,
            "ask_json",
            lambda *a, **k: {
                "date_column": "date",
                "period_unit": "quarter",
                "current_period": "Q3-2026",
                "prior_period": "Q2-2026",
                "definition_text": "current vs prior quarter",
            },
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            period = builder.resolve_period(df, "schema")
        # max date 2026-08-02 -> most recent complete quarter is Q2 2026
        assert period["current_start"] == "2026-04-01"
        assert period["current_end"] == "2026-06-30"


class TestDateDetection:
    def test_detect_date_columns_picks_iso_and_ignores_ids(self):
        import warnings

        df = pd.DataFrame(
            {
                "opportunity_id": ["0P4AAPYX", "Z063OYW0", "EC4QE1BX"],
                "engage_date": ["2016-10-20", "2016-10-25", "2016-10-25"],
                "product": ["A", "B", "A"],
            }
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any emitted warning fails the test
            cols = builder._detect_date_columns(df)
        assert cols == ["engage_date"]

    def test_detect_date_columns_datetime_dtype_fast_path(self):
        df = _sample_df()  # date column already datetime64
        assert builder._detect_date_columns(df) == ["date"]


class TestMetricBrief:
    def test_brief_without_values(self):
        brief = builder.format_priority_metric_brief(_sample_pri())
        assert "PRE-COMPUTED VALUES" not in brief

    def test_brief_with_values(self):
        values = {"Growth": {"value": 0.5, "unit": "ratio", "period": "Aug-2026", "status": "computed", "verified": False}}
        brief = builder.format_priority_metric_brief(_sample_pri(), values=values)
        assert "PRE-COMPUTED VALUES" in brief
        assert "Growth" in brief
        assert "UNVERIFIED" in brief


class TestDataLimitedPreFilter:
    def test_stage_progression_phrasings(self):
        for text in (
            "advancing to the next stage",
            "progressing through the next stage",
            "stage progression rate",
            "stage-to-stage velocity",
            "days spent in stage",
            "time per stage",
        ):
            reason, prim = builder._non_scalar_reason(text)
            assert reason, text
            assert prim == "requires stage-entry/transition timestamps"

    def test_expressible_measurements_not_filtered(self):
        for text in (
            "current count vs prior count",
            "mean win rate across agents",
            "top 20% of products by revenue",
            "new account acquisition rate",
        ):
            reason, _ = builder._non_scalar_reason(text)
            assert not reason, text


class TestComputabilityRuleBook:
    def test_friendly_reason_maps_technical_jargon(self):
        assert "zero" in builder.friendly_reason("no prior-period baseline (prior value is 0)")
        assert "no earlier period" in builder.friendly_reason("no prior-period baseline (prior value is 0)")
        assert "prior comparison period" in builder.friendly_reason(
            "the prior comparison period contains no data, so a period-over-period change cannot be computed"
        )
        assert "form" in builder.friendly_reason("metric omitted or not produced in output")
        assert "not computed" in builder.friendly_reason(
            "some unknown reason"
        ).lower() or "some unknown reason" == builder.friendly_reason("some unknown reason")

    def test_friendly_reason_never_contains_prior_value_zero(self):
        # The raw technical string must not leak to users.
        raw = "no prior-period baseline (prior value is 0)"
        display = builder.friendly_reason(raw)
        assert "prior value is 0" not in display
        assert "prior-period" not in display

    def test_delta_measurement_detection(self):
        assert builder._is_delta_measurement("Percentage change in the count of opportunities compared to the prior period")
        assert builder._is_delta_measurement("Revenue growth vs prior period")
        assert not builder._is_delta_measurement("current count of active accounts")
        assert not builder._is_delta_measurement("count of rows in current period")

    def test_precheck_no_time_dimension_rejects_delta(self):
        period = _period()
        period["date_column"] = None
        period["prior_start"] = None
        reason, _ = builder._precheck_measurement(
            "Percentage change in the count of opportunities compared to the prior period", period
        )
        assert reason and "time" in reason

    def test_precheck_empty_prior_window_rejects_delta(self):
        period = _period()
        period["prior_start"] = "2016-01-01"
        period["prior_end"] = "2016-01-31"
        reason, prim = builder._precheck_measurement(
            "Percentage change in the count of opportunities compared to the prior period", period, df=_sample_df()
        )
        assert reason and "prior comparison period" in reason
        assert prim == "empty prior period"

    def test_precheck_level_metric_not_rejected_without_time(self):
        period = _period()
        period["date_column"] = None
        period["prior_start"] = None
        reason, _ = builder._precheck_measurement("current count of active accounts", period)
        assert not reason

    def test_nc_record_carries_plain_display(self):
        period = _period()
        rec = builder._nc_record(period, "measurement text", "no prior-period baseline (prior value is 0)")
        assert rec["status"] == "not_computable"
        assert rec["reason_display"] and "prior value is 0" not in rec["reason_display"]

    def test_compute_prefilters_no_time_dimension_delta(self, monkeypatch):
        period = _period()
        period["date_column"] = None
        period["prior_start"] = None
        monkeypatch.setattr(builder, "resolve_period", lambda *a, **k: period)
        dc_spec = {
            "name": "Deal Count",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "count",
        }
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: [dc_spec])
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert "Growth" not in values
        assert skipped["Growth"]["reason"] and builder.friendly_reason(skipped["Growth"]["reason"])
        # Deal Count is a LEVEL count — legitimately computable without a time dimension.
        assert values["Deal Count"]["status"] == "computed"

    def test_no_substitution_never_produces_wrong_value_kind(self, monkeypatch):
        # A % metric with an empty prior must NOT degrade to a level/raw count.
        period = _period()
        period["prior_start"] = "2016-01-01"
        period["prior_end"] = "2016-01-31"
        monkeypatch.setattr(builder, "resolve_period", lambda *a, **k: period)
        spec = {
            "name": "Growth",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "pct_change",
            "unit": "count",
        }
        calls = iter([[spec], [spec]])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert "Growth" not in values
        assert skipped["Growth"]["reason"]


class TestComputePriorityValues:
    def test_compute_ok(self, monkeypatch):
        calls = iter([_period(), _specs()])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        pri_rec = result["priorities"]["Growth"]
        values = pri_rec["values"]
        assert len(result["generated_at"]) > 0
        assert len(result["data_fingerprint"]) == 64
        assert pri_rec["fingerprint"] == builder.priority_fingerprint(_sample_pri())
        assert values["Growth"]["status"] == "computed"
        assert isinstance(values["Growth"]["value"], float)
        assert values["Deal Count"]["status"] == "computed"
        assert values["Deal Count"]["value"] == 2

    def test_compute_omitted_metric_retried_then_not_computable(self, monkeypatch):
        # Attempt 1 omits "Deal Count" -> NOT dropped immediately; attempt 2 re-asks.
        # Still omitted after attempt 2 -> honestly not_computable.
        calls = iter(
            [
                _period(),
                [_specs()[0]],
                [_specs()[0]],
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert values["Growth"]["status"] == "computed"
        assert "Deal Count" not in values
        assert "scalar spec" in skipped["Deal Count"]["reason"]

    def test_compute_omitted_metric_repaired_on_second_attempt(self, monkeypatch):
        # Omitted on attempt 1, supplied on attempt 2 -> computed (repair pass catches it).
        calls = iter(
            [
                _period(),
                [_specs()[0]],
                _specs(),
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        assert values["Growth"]["status"] == "computed"
        assert values["Deal Count"]["status"] == "computed"

    def test_compute_invalid_spec_is_repaired(self, monkeypatch):
        # Attempt 1 returns a Deal Count spec that fails validation -> attempt 2 repairs it.
        bad = dict(_specs()[1], agg="bogus")
        calls = iter(
            [
                _period(),
                [_specs()[0], bad],
                _specs(),
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        assert values["Growth"]["status"] == "computed"
        assert values["Deal Count"]["status"] == "computed"

    def test_compute_resumes_existing(self, monkeypatch):
        # A stored "Deal Count" record is reused; only "Growth" is computed.
        existing = {
            "Deal Count": {
                "value": 42,
                "unit": "count",
                "status": "computed",
                "verified": False,
            }
        }
        calls = iter(
            [
                _period(),
                [_specs()[0]],
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema", existing=existing)
        values = result["priorities"]["Growth"]["values"]
        assert values["Deal Count"]["value"] == 42
        assert values["Growth"]["status"] == "computed"

    def test_compute_on_progress_per_group(self, monkeypatch):
        # on_progress is called once per metric group (KPI + its operational metrics)
        # with the full result dict.
        pri = _sample_pri()
        pri["kpis"].append(
            {
                "name": "Second",
                "metric": "date",
                "measurement": "count in current period",
                "operational_metrics": [],
            }
        )
        sec_spec = {
            "name": "Second",
            "agg": "count",
            "value_column": None,
            "condition": None,
            "numerator": None,
            "denominator": None,
            "group_by": None,
            "k": None,
            "compare": "level",
            "unit": "count",
        }
        calls = iter(
            [
                _period(),
                _specs(),
                [sec_spec],
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        snapshots = []
        result = builder.compute_priority_values(pri, _sample_df(), "schema", on_progress=snapshots.append)
        assert len(snapshots) == 2
        assert "Growth" in snapshots[0]["priorities"]["Growth"]["values"]
        assert "Second" in snapshots[1]["priorities"]["Growth"]["values"]
        assert "Growth" in result["priorities"]["Growth"]["values"]
        assert "Second" in result["priorities"]["Growth"]["values"]

    def test_compute_per_group_metric_computed_via_steps(self, monkeypatch):
        # Per-group measurements now FLOW to the LLM (expressible via the operator DSL);
        # a steps spec makes it computable instead of pre-filtered.
        pri = {
            "name": "Growth",
            "kpis": [
                {
                    "name": "Growth",
                    "metric": "date",
                    "measurement": "current count vs prior count",
                    "operational_metrics": [
                        {
                            "name": "Per Agent",
                            "metric": "agent",
                            "measurement": "Average count per agent, period-over-period change",
                        }
                    ],
                }
            ],
        }
        steps_spec = {
            "name": "Per Agent",
            "steps": [{"op": "group", "group_by": "agent", "inner_agg": "count", "value": None, "outer_agg": "mean"}],
            "compare": "pct_change",
            "unit": "count",
        }
        calls = iter(
            [
                _period(),
                [_specs()[0], steps_spec],
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(pri, _group_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        assert values["Per Agent"]["status"] == "computed"
        assert abs(values["Per Agent"]["value"] - 0.0) < 1e-9  # 2 vs 2 counts -> (2-2)/2
        assert values["Growth"]["status"] == "computed"

    def test_compute_data_limited_prefiltered_with_primitive(self, monkeypatch):
        # Residual data-limited measurement -> hard-filtered with missing_primitive.
        pri = {
            "name": "Growth",
            "kpis": [
                {
                    "name": "Growth",
                    "metric": "date",
                    "measurement": "current count vs prior count",
                    "operational_metrics": [
                        {
                            "name": "Stage Velocity",
                            "metric": "date",
                            "measurement": "Time-in-Stage Velocity: average days spent in each stage",
                        }
                    ],
                }
            ],
        }
        calls = iter(
            [
                _period(),
                [_specs()[0]],
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(pri, _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert skipped["Stage Velocity"]["missing_primitive"] == "requires stage-entry/transition timestamps"
        assert values["Growth"]["status"] == "computed"

    def test_compute_missing_metric_is_not_computable(self, monkeypatch):
        calls = iter(
            [
                _period(),
                [_specs()[0]],
                [_specs()[0]],
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert values["Growth"]["status"] == "computed"
        assert "Deal Count" not in values
        assert skipped["Deal Count"]["reason"]

    def test_compute_null_value_is_not_computable(self, monkeypatch):
        null_spec = dict(_specs()[0], compare="pct_change")
        calls = iter(
            [
                [null_spec, _specs()[1]],
            ]
        )
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        # prior period (Jan-Feb) has rows; make it empty so pct_change yields null
        period = _period()
        period["prior_start"] = "2016-01-01"
        period["prior_end"] = "2016-01-31"
        monkeypatch.setattr(builder, "resolve_period", lambda *a, **k: period)
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert "Growth" not in values
        assert skipped["Growth"]["reason"]
        assert values["Deal Count"]["status"] == "computed"

    def test_compute_zero_prior_null_reason(self, monkeypatch):
        # pct_change with an empty prior period -> skipped with a plain-language
        # reason (rule book: no substitution, no fabricated 0).
        period = _period()
        period["prior_start"] = "2016-01-01"
        period["prior_end"] = "2016-01-31"
        monkeypatch.setattr(builder, "resolve_period", lambda *a, **k: period)
        calls = iter([_specs()])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert "Growth" not in values
        assert "prior comparison period" in skipped["Growth"]["reason"]
        assert values["Deal Count"]["status"] == "computed"

    def test_compute_persists_spec(self, monkeypatch):
        calls = iter([_period(), _specs()])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        assert values["Growth"]["spec"]["agg"] == "count"
        assert values["Growth"]["spec"]["compare"] == "pct_change"
        assert "spec" in values["Deal Count"]

    def test_compute_persists_period_bounds(self, monkeypatch):
        calls = iter([_period(), _specs()])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        assert result["period"]["date_column"] == "date"
        assert result["period"]["current_start"] == "2026-08-01"
        assert result["period"]["prior_end"] == "2026-02-28"

    def test_compute_sets_verification(self, monkeypatch):
        calls = iter([_period(), _specs()])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        assert values["Growth"]["verified"] is True
        assert [c["layer"] for c in values["Growth"]["verification"]["checks"]] == ["l0", "l1"]
        assert values["Deal Count"]["verified"] is True

    def test_compute_bad_spec_is_not_computable(self, monkeypatch):
        bad = dict(_specs()[0], agg="bogus")
        calls = iter([_period(), [bad], [bad]])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert "Growth" not in values
        assert skipped["Growth"]["reason"]

    def test_compute_script_failure_is_error(self, monkeypatch):
        calls = iter([_period(), _specs(), _specs()])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        monkeypatch.setattr(builder.sandbox, "execute_code", lambda *a, **k: (False, "boom: simulated sandbox failure"))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        skipped = result["priorities"]["Growth"]["skipped"]
        assert "Growth" not in values
        assert skipped["Growth"]["status"] == "error"
        assert skipped["Deal Count"]["status"] == "error"


def _run(specs, df=_group_df(), period=_period()):
    code = builder.build_metric_script(specs, period)
    ok, out = sandbox.execute_code(code, df)
    assert ok, out
    return builder._parse_compute_output(out)


def _group_spec(name, inner, outer, value="value", compare="level", unit="ratio", group_by="agent"):
    return {
        "name": name,
        "steps": [{"op": "group", "group_by": group_by, "inner_agg": inner, "value": value, "outer_agg": outer}],
        "compare": compare,
        "unit": unit,
    }


class TestOperatorDSL:
    def test_group_mean_of_counts(self):
        parsed = _run([_group_spec("AvgPerAgent", "count", "mean")])
        assert abs(parsed["AvgPerAgent"]["value"] - 2.0) < 1e-9  # A:2, B:2 -> mean 2

    def test_group_std_of_means(self):
        parsed = _run([_group_spec("StdOfMeans", "mean", "std")])
        # current means A=15, B=35 -> sample std
        import numpy as np

        assert abs(parsed["StdOfMeans"]["value"] - np.std([15.0, 35.0], ddof=1)) < 1e-9

    def test_group_max_of_shares(self):
        parsed = _run([_group_spec("MaxShare", "share", "max")])
        # current totals: A=30, B=70 of 100 -> shares 0.3, 0.7 -> max 0.7
        assert abs(parsed["MaxShare"]["value"] - 0.7) < 1e-9

    def test_group_pct_change(self):
        parsed = _run([_group_spec("PctChange", "count", "mean", compare="pct_change")])
        # current 2,2 -> 2 ; prior 2,2 -> 2 ; (2-2)/2 = 0
        assert abs(parsed["PctChange"]["value"] - 0.0) < 1e-9

    def test_group_count_uses_size_not_column(self):
        # inner_agg count with value=None must not touch a value column
        spec = dict(
            _group_spec("CountOnly", "count", "sum"),
            steps=[{"op": "group", "group_by": "agent", "inner_agg": "count", "value": None, "outer_agg": "sum"}],
        )
        parsed = _run([spec])
        assert abs(parsed["CountOnly"]["value"] - 4.0) < 1e-9  # 2 + 2

    def test_validate_group_bad_inner(self):
        spec = dict(
            _group_spec("X", "count", "mean"),
            steps=[{"op": "group", "group_by": "agent", "inner_agg": "bogus", "value": None, "outer_agg": "mean"}],
        )
        ok, msg = builder._validate_spec(spec, {"agent", "value"})
        assert not ok and "inner_agg" in msg

    def test_validate_agg_and_steps_rejected(self):
        spec = dict(_group_spec("X", "count", "mean"), agg="count")
        ok, msg = builder._validate_spec(spec, {"agent", "value"})
        assert not ok and "not both" in msg

    def test_group_missing_outer_agg_defaults_and_runs(self):
        spec = {
            "name": "AvgPerAgent",
            "steps": [{"op": "group", "group_by": "agent", "inner_agg": "count", "value": None}],
            "compare": "level",
            "unit": "count",
        }
        ok, msg = builder._validate_spec(spec, {"agent", "value"})
        assert ok, msg
        parsed = _run([spec])
        assert abs(parsed["AvgPerAgent"]["value"] - 2.0) < 1e-9  # A:2, B:2 -> mean 2


class TestDerive:
    def test_derive_days_between_group(self):
        spec = {
            "name": "CycleTime",
            "prep": [{"op": "derive.days_between", "start": "engage", "end": "close", "as": "cycle_days"}],
            "steps": [{"op": "group", "group_by": "date", "inner_agg": "mean", "value": "cycle_days", "outer_agg": "mean"}],
            "compare": "level",
            "unit": "days",
        }
        parsed = _run([spec], df=_derive_df())
        # cycle_days: 31, 22, 14 -> per-date means -> mean 67/3
        assert abs(parsed["CycleTime"]["value"] - (31 + 22 + 14) / 3) < 1e-9

    def test_derive_arithmetic_group(self):
        spec = {
            "name": "DoubleQty",
            "prep": [{"op": "derive.arithmetic", "expr": "qty * 2", "as": "double"}],
            "steps": [{"op": "group", "group_by": "date", "inner_agg": "sum", "value": "double", "outer_agg": "mean"}],
            "compare": "level",
            "unit": "count",
        }
        parsed = _run([spec], df=_derive_df())
        # sums 4, 6, 10 -> mean 20/3
        assert abs(parsed["DoubleQty"]["value"] - 20 / 3) < 1e-9

    def test_derive_arithmetic_rejects_unknown_name(self):
        ok, msg = builder._check_expression("qty + nope", {"qty"})
        assert not ok and "nope" in msg

    def test_validate_derive_collides_with_column(self):
        spec = {
            "name": "X",
            "prep": [{"op": "derive.month_of", "column": "date", "as": "date"}],
            "steps": [{"op": "group", "group_by": "date", "inner_agg": "count", "value": None, "outer_agg": "mean"}],
            "compare": "level",
            "unit": "count",
        }
        ok, msg = builder._validate_spec(spec, {"date"})
        assert not ok and "collides" in msg

    def test_validate_derive_bad_date_column(self):
        spec = {
            "name": "X",
            "prep": [{"op": "derive.days_between", "start": "engage", "end": "nope", "as": "cyc"}],
            "steps": [{"op": "group", "group_by": "date", "inner_agg": "mean", "value": "cyc", "outer_agg": "mean"}],
            "compare": "level",
            "unit": "days",
        }
        ok, msg = builder._validate_spec(spec, {"date", "engage"})
        assert not ok and "not in schema" in msg


class TestWindowAndPercentile:
    def test_count_distinct_top_level(self):
        spec = {"name": "Agents", "agg": "count_distinct", "value_column": "agent", "compare": "level", "unit": "count"}
        parsed = _run([spec])
        assert parsed["Agents"]["value"] == 2  # A, B in current period

    def test_share_with_count_distinct_denominator(self):
        spec = {
            "name": "DealsPerAgent",
            "agg": "share",
            "numerator": {"agg": "count", "value_column": None, "condition": None},
            "denominator": {"agg": "count_distinct", "value_column": "agent", "condition": None},
            "compare": "level",
            "unit": "ratio",
        }
        parsed = _run([spec])
        assert abs(parsed["DealsPerAgent"]["value"] - 4 / 2) < 1e-9

    def test_new_first_time_in_current_period(self):
        spec = {"name": "NewAgents", "steps": [{"op": "new", "value_column": "agent"}], "compare": "level", "unit": "count"}
        parsed = _run([spec], df=_new_df())
        # current = {C, A}; seen before current_start = {A, B} -> new = {C}
        assert parsed["NewAgents"]["value"] == 1

    def test_new_degenerates_to_distinct_without_history(self):
        spec = {"name": "NewAll", "steps": [{"op": "new", "value_column": "agent"}], "compare": "level", "unit": "count"}
        df = pd.DataFrame({"date": pd.to_datetime(["2026-08-01", "2026-08-02"]), "agent": ["A", "B"]})
        parsed = _run([spec], df=df)
        assert parsed["NewAll"]["value"] == 2

    def test_new_prior_value(self):
        spec = {"name": "NewAgentsPct", "steps": [{"op": "new", "value_column": "agent"}], "compare": "pct_change", "unit": "count"}
        parsed = _run([spec], df=_new_df())
        # current new = 1 (C); prior (Jan-Feb) new = 2 (A, B both first in prior) -> (1-2)/2
        assert abs(parsed["NewAgentsPct"]["value"] - (1 - 2) / 2) < 1e-9

    def test_fractional_topk_share(self):
        spec = {
            "name": "TopHalf",
            "agg": "topk_share",
            "value_column": "value",
            "group_by": "agent",
            "k": 0.5,
            "compare": "level",
            "unit": "ratio",
        }
        parsed = _run([spec])
        # top 50% of 2 agents = top 1 -> B (70/100)
        assert abs(parsed["TopHalf"]["value"] - 0.7) < 1e-9

    def test_validate_fractional_topk_bounds(self):
        ok, _ = builder._validate_spec(
            {
                "name": "X",
                "agg": "topk_share",
                "value_column": "value",
                "group_by": "agent",
                "k": 0.5,
                "compare": "level",
                "unit": "ratio",
            },
            {"agent", "value"},
        )
        assert ok
        ok, msg = builder._validate_spec(
            {
                "name": "X",
                "agg": "topk_share",
                "value_column": "value",
                "group_by": "agent",
                "k": 1.5,
                "compare": "level",
                "unit": "ratio",
            },
            {"agent", "value"},
        )
        assert not ok and "k" in msg


class TestCustomSpec:
    def test_custom_spec_runs(self):
        spec = {"name": "Custom", "kind": "custom", "code": "_c = float(len(df.loc[_CUR]))", "compare": "level", "unit": "count"}
        parsed = _run([spec], df=_sample_df())
        assert parsed["Custom"]["value"] == 2

    def test_custom_code_rejected_import(self):
        spec = {"name": "Custom", "kind": "custom", "code": "import os\n_c = 1", "compare": "level", "unit": "count"}
        ok, msg = builder._validate_spec(spec, {"date"})
        assert not ok

    def test_custom_source_flag(self, monkeypatch):
        pri = {
            "name": "Growth",
            "kpis": [{"name": "Custom", "metric": "date", "measurement": "custom calc", "operational_metrics": []}],
        }
        custom_spec = {
            "name": "Custom",
            "kind": "custom",
            "code": "_c = float(len(df.loc[_CUR]))",
            "compare": "level",
            "unit": "count",
        }
        calls = iter([_period(), [custom_spec]])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(pri, _sample_df(), "schema")
        values = result["priorities"]["Growth"]["values"]
        assert values["Custom"]["status"] == "computed"
        assert values["Custom"]["source"] == "custom"


class TestInputRef:
    def test_input_ref_composes_measure(self):
        specs = [
            {
                "name": "Count",
                "agg": "count",
                "value_column": None,
                "condition": None,
                "numerator": None,
                "denominator": None,
                "group_by": None,
                "k": None,
                "compare": "level",
                "unit": "count",
            },
            {"name": "CopyOfCount", "input_ref": "Count", "compare": "level", "unit": "count"},
        ]
        parsed = _run(specs, df=_sample_df())
        assert parsed["CopyOfCount"]["value"] == parsed["Count"]["value"] == 2

    def test_input_ref_requires_level(self):
        spec = {"name": "Copy", "input_ref": "Count", "compare": "pct_change", "unit": "count"}
        ok, msg = builder._validate_spec(spec, {"date"}, batch_names={"Count"})
        assert not ok and "level" in msg

    def test_input_ref_requires_batch_member(self):
        spec = {"name": "Copy", "input_ref": "Nope", "compare": "level", "unit": "count"}
        ok, msg = builder._validate_spec(spec, {"date"}, batch_names={"Count"})
        assert not ok and "input_ref" in msg


class TestEngineVersion:
    def test_compute_result_carries_engine_version(self, monkeypatch):
        calls = iter([_period(), _specs()])
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: next(calls))
        result = builder.compute_priority_values(_sample_pri(), _sample_df(), "schema")
        assert result["engine_version"] == builder.COMPUTE_ENGINE_VERSION

    def test_shell_stale_on_engine_version_mismatch(self):
        from src.analyst.shell import AnalystShell

        class _FakeProject:
            def __init__(self, pv):
                self.priority_values = pv

        shell = AnalystShell.__new__(AnalystShell)
        shell.df = _sample_df()
        stored = {
            "engine_version": "engine-old",
            "data_fingerprint": builder.data_fingerprint(_sample_df()),
            "priorities": {
                "Growth": {
                    "fingerprint": builder.priority_fingerprint(_sample_pri()),
                    "values": {"Growth": {"status": "computed"}, "Deal Count": {"status": "computed"}},
                }
            },
        }
        shell.project = _FakeProject(stored)
        assert not shell._priority_values_are_current(_sample_pri())

    def test_shell_current_on_engine_version_match(self):
        from src.analyst.shell import AnalystShell

        class _FakeProject:
            def __init__(self, pv):
                self.priority_values = pv

        shell = AnalystShell.__new__(AnalystShell)
        shell.df = _sample_df()
        stored = {
            "engine_version": builder.COMPUTE_ENGINE_VERSION,
            "data_fingerprint": builder.data_fingerprint(_sample_df()),
            "priorities": {
                "Growth": {
                    "fingerprint": builder.priority_fingerprint(_sample_pri()),
                    "engine_version": builder.COMPUTE_ENGINE_VERSION,
                    "values": {"Growth": {"status": "computed"}, "Deal Count": {"status": "computed"}},
                }
            },
        }
        shell.project = _FakeProject(stored)
        assert shell._priority_values_are_current(_sample_pri())

    def test_shell_does_not_resume_when_engine_changed(self, monkeypatch):
        from src.analyst.shell import AnalystShell

        class _FakeProject:
            def __init__(self, pv):
                self.priority_values = pv

            def save(self):
                pass

        shell = AnalystShell.__new__(AnalystShell)
        shell.df = _sample_df()
        stored = {
            "engine_version": "engine-old",
            "data_fingerprint": builder.data_fingerprint(_sample_df()),
            "period_definition": "current vs prior",
            "priorities": {
                "Growth": {
                    "fingerprint": builder.priority_fingerprint(_sample_pri()),
                    "values": {
                        "Growth": {"value": 1.0, "unit": "count", "status": "computed", "verified": False},
                        "Deal Count": {"value": 2.0, "unit": "count", "status": "computed", "verified": False},
                    },
                }
            },
        }
        shell.project = _FakeProject(stored)
        captured = {}

        def fake_compute(pri, df, schema_str, existing=None, existing_skipped=None, on_progress=None, period=None):
            captured["existing"] = existing
            return {
                "generated_at": "t",
                "data_fingerprint": "d",
                "engine_version": builder.COMPUTE_ENGINE_VERSION,
                "period_definition": "p",
                "priorities": {"Growth": {"values": {}}},
            }

        monkeypatch.setattr(builder, "compute_priority_values", fake_compute)
        monkeypatch.setattr(builder, "extract_schema", lambda df: "schema")
        shell._ensure_priority_values(_sample_pri())
        assert captured["existing"] is None
        assert shell.project.priority_values["engine_version"] == builder.COMPUTE_ENGINE_VERSION

    def test_shell_resumes_when_base_current(self, monkeypatch):
        from src.analyst.shell import AnalystShell

        class _FakeProject:
            def __init__(self, pv):
                self.priority_values = pv

            def save(self):
                pass

        shell = AnalystShell.__new__(AnalystShell)
        shell.df = _sample_df()
        values = {"Growth": {"value": 1.0, "unit": "count", "status": "computed", "verified": False}}
        stored = {
            "engine_version": builder.COMPUTE_ENGINE_VERSION,
            "data_fingerprint": builder.data_fingerprint(_sample_df()),
            "period_definition": "current vs prior",
            "priorities": {
                "Growth": {
                    "fingerprint": builder.priority_fingerprint(_sample_pri()),
                    "engine_version": builder.COMPUTE_ENGINE_VERSION,
                    "values": values,
                }
            },
        }
        shell.project = _FakeProject(stored)
        captured = {}

        def fake_compute(pri, df, schema_str, existing=None, existing_skipped=None, on_progress=None, period=None):
            captured["existing"] = existing
            return {
                "generated_at": "t",
                "data_fingerprint": "d",
                "engine_version": builder.COMPUTE_ENGINE_VERSION,
                "period_definition": "p",
                "priorities": {"Growth": {"values": {}}},
            }

        monkeypatch.setattr(builder, "compute_priority_values", fake_compute)
        monkeypatch.setattr(builder, "extract_schema", lambda df: "schema")
        shell._ensure_priority_values(_sample_pri())
        assert captured["existing"] == values


def _level_count_spec(value=None):
    return {"agg": "count", "value_column": value, "condition": None, "compare": "level", "unit": "count"}


class TestVerifyTier:
    def test_check_value_negative_level_count(self):
        rec = {"value": -1.0, "unit": "count", "spec": _level_count_spec()}
        ok, note = builder._check_value(rec)
        assert not ok and "negative" in note

    def test_check_value_share_out_of_bounds(self):
        rec = {"value": 1.5, "unit": "ratio", "spec": {"agg": "share", "compare": "level"}}
        ok, _ = builder._check_value(rec)
        assert not ok

    def test_check_value_share_in_bounds(self):
        rec = {"value": 0.5, "unit": "ratio", "spec": {"agg": "share", "compare": "level"}}
        ok, _ = builder._check_value(rec)
        assert ok

    def test_check_value_pct_change_can_be_negative(self):
        rec = {"value": -0.5, "unit": "ratio", "spec": {"agg": "count", "compare": "pct_change"}}
        ok, _ = builder._check_value(rec)
        assert ok

    def test_check_value_non_finite(self):
        rec = {"value": float("inf"), "unit": "count", "spec": _level_count_spec()}
        ok, note = builder._check_value(rec)
        assert not ok and "finite" in note

    def test_recompute_level_count(self):
        assert builder._recompute_value(_sample_df(), _period(), _level_count_spec()) == 2.0

    def test_recompute_sum(self):
        spec = {"agg": "sum", "value_column": "value", "condition": None, "compare": "level", "unit": "currency"}
        assert builder._recompute_value(_sample_df(), _period(), spec) == 7.0

    def test_recompute_pct_change(self):
        spec = {"agg": "count", "value_column": None, "condition": None, "compare": "pct_change", "unit": "ratio"}
        val = builder._recompute_value(_sample_df(), _period(), spec)
        assert abs(val) < 1e-12  # 2 vs 2

    def test_recompute_with_condition(self):
        spec = {"agg": "count", "value_column": None, "condition": "df['value'] > 2", "compare": "level", "unit": "count"}
        assert builder._recompute_value(_sample_df(), _period(), spec) == 2.0  # 3, 4

    def test_recompute_skips_composed(self):
        spec = {
            "steps": [{"op": "group", "group_by": "agent", "inner_agg": "count", "value": None, "outer_agg": "mean"}],
            "compare": "level",
            "unit": "count",
        }
        assert builder._recompute_value(_group_df(), _period(), spec) is None

    def test_verify_layers_sets_verified(self):
        values = {"Growth": {"status": "computed", "value": 2.0, "unit": "count", "spec": _level_count_spec()}}
        updated, summary = builder._verify_layers(values, _sample_df(), _period())
        assert updated["Growth"]["verified"] is True
        assert summary["l0"]["pass"] == 1
        assert summary["l1"]["match"] == 1
        assert [c["layer"] for c in updated["Growth"]["verification"]["checks"]] == ["l0", "l1"]

    def test_verify_layers_flags_recompute_mismatch(self):
        values = {"Growth": {"status": "computed", "value": 99.0, "unit": "count", "spec": _level_count_spec()}}
        updated, summary = builder._verify_layers(values, _sample_df(), _period())
        assert updated["Growth"]["verified"] is False
        assert summary["l1"]["mismatch"] == 1

    def test_verify_layers_flags_negative_level_count(self):
        values = {"Growth": {"status": "computed", "value": -1.0, "unit": "count", "spec": _level_count_spec()}}
        updated, _ = builder._verify_layers(values, _sample_df(), _period())
        assert updated["Growth"]["verified"] is False

    def test_verify_priority_values_llm_unsets(self, monkeypatch):
        values = {
            "Growth": {
                "status": "computed",
                "value": 2.0,
                "unit": "count",
                "verified": True,
                "measurement": "current count vs prior count",
                "spec": _level_count_spec(),
            },
            "Deal Count": {
                "status": "computed",
                "value": 2.0,
                "unit": "count",
                "verified": True,
                "measurement": "count of rows",
                "spec": _level_count_spec(),
            },
        }
        monkeypatch.setattr(
            builder.llm,
            "ask_json",
            lambda *a, **k: {"Growth": {"ok": False, "note": "wrong basis"}, "Deal Count": {"ok": True, "note": "fine"}},
        )
        period = dict(_period(), definition_text="current vs prior")
        out = builder.verify_priority_values(_sample_pri(), _sample_df(), values, period, "schema")
        assert out["Growth"]["verified"] is False
        assert out["Growth"]["verification"]["llm_note"] == "wrong basis"
        assert out["Deal Count"]["verified"] is True

    def test_verify_priority_values_skips_non_computed(self, monkeypatch):
        values = {"Growth": {"status": "not_computable", "value": None, "unit": "", "verified": False}}
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: {})
        period = dict(_period(), definition_text="p")
        out = builder.verify_priority_values(_sample_pri(), _sample_df(), values, period, "schema")
        assert out["Growth"] == values["Growth"]

    def test_shell_verify_persists_verdicts(self, monkeypatch):
        from src.analyst.shell import AnalystShell

        class _FakeProject:
            def __init__(self, pv):
                self.priority_values = pv

            def save(self):
                pass

        values = {
            "Growth": {
                "value": 2.0,
                "unit": "count",
                "status": "computed",
                "verified": True,
                "measurement": "current count vs prior count",
                "basis": "current 2 vs prior 2",
                "spec": _level_count_spec(),
            },
            "Deal Count": {
                "value": 2.0,
                "unit": "count",
                "status": "computed",
                "verified": True,
                "measurement": "count of rows in current period",
                "basis": "current 2",
                "spec": _level_count_spec(),
            },
        }
        pv = {
            "engine_version": builder.COMPUTE_ENGINE_VERSION,
            "data_fingerprint": builder.data_fingerprint(_sample_df()),
            "period_definition": "current vs prior",
            "period": {
                "date_column": "date",
                "current_start": "2026-08-01",
                "current_end": "2026-08-31",
                "prior_start": "2026-01-01",
                "prior_end": "2026-02-28",
            },
            "priorities": {
                "Growth": {
                    "fingerprint": builder.priority_fingerprint(_sample_pri()),
                    "engine_version": builder.COMPUTE_ENGINE_VERSION,
                    "values": values,
                }
            },
        }
        shell = AnalystShell.__new__(AnalystShell)
        shell.project = _FakeProject(pv)
        shell.df = _sample_df()
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: {"Growth": {"ok": False, "note": "wrong basis"}})
        shell._verify_priority_values(_sample_pri())
        stored = shell.project.priority_values["priorities"]["Growth"]["values"]["Growth"]
        assert stored["verified"] is False
        assert stored["verification"]["llm_ok"] is False
        assert stored["verification"]["llm_note"] == "wrong basis"


class TestLLMClientParams:
    def _fake_client(self, monkeypatch, responses):
        calls = []

        class _Msg:
            def __init__(self, content):
                self.content = content
                self.reasoning_content = None

        class _Choice:
            def __init__(self, content):
                self.message = _Msg(content)

        class _Resp:
            def __init__(self, content):
                self.choices = [_Choice(content)]

        class _Completions:
            def create(self, **kwargs):
                calls.append(kwargs)
                return _Resp(responses[len(calls) - 1])

        class _Chat:
            def __init__(self):
                self.completions = _Completions()

        class _Client:
            def __init__(self):
                self.chat = _Chat()

        monkeypatch.setattr(llm, "get_client", _Client)
        return calls

    def test_ask_forwards_max_tokens_and_thinking_budget(self, monkeypatch):
        calls = self._fake_client(monkeypatch, ["ok"])
        out = llm.ask("q", label="t")
        assert out == "ok"
        assert calls[0]["max_tokens"] == llm.CONFIG.max_tokens
        assert calls[0]["extra_body"]["thinking_budget_tokens"] == llm.CONFIG.thinking_budget_tokens

    def test_chat_with_tools_forwards_thinking_budget_but_no_max_tokens(self, monkeypatch):
        calls = self._fake_client(monkeypatch, ["ok"])
        llm.chat_with_tools([{"role": "user", "content": "hi"}], tools=[], label="t")
        assert calls[0]["extra_body"]["thinking_budget_tokens"] == llm.CONFIG.thinking_budget_tokens
        assert "max_tokens" not in calls[0]

    def test_ask_json_sends_budget_through_ask(self, monkeypatch):
        calls = self._fake_client(monkeypatch, ['{"a": 1}'])
        out = llm.ask_json("q", label="t")
        assert out == {"a": 1}
        assert calls[0]["extra_body"]["thinking_budget_tokens"] == llm.CONFIG.thinking_budget_tokens
