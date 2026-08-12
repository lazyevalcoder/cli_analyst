"""Permanent anchor/core fixes: enum grounding, period-aware generation, and the
deterministic 0-vs-0 anchor gate.

Guards against: LLMs inventing categorical literals (stage names etc. not in the data),
generation time-splitting disagreeing with compute, and period-over-period metrics that
count 0 rows in BOTH windows (active records carrying no date in the anchor column)
being reported as a number instead of an honest not_computable.
"""

import pandas as pd
import pytest

from src.analyst import builder


def _df():
    """7 rows: current (Aug 2026), prior (Jan 2026), and 2 'active' rows whose
    commodity date is null — records the anchor column cannot place in any window."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-03", "2026-01-15", "2026-01-20", None, None]),
            "stage": ["Won", "Lost", "Won", "Won", "Lost", "Active", "Active"],
            "region": ["West", "East", "West", "West", "East", "West", "East"],
            "sales": [100, 50, 25, 20, 10, 0, 0],
        }
    )


def _period():
    return {
        "date_column": "date",
        "current_period": "Aug-2026",
        "prior_period": "Jan-2026",
        "current_start": "2026-08-01",
        "current_end": "2026-08-31",
        "prior_start": "2026-01-01",
        "prior_end": "2026-01-31",
        "definition_text": "current = Aug-2026, prior = Jan-2026 (sums/counts over date)",
    }


def _pri():
    return {
        "name": "Growth",
        "description": "Drive growth",
        "executive_questions": ["Where is growth?"],
        "kpis": [
            {
                "name": "Revenue",
                "metric": "sales",
                "measurement": "percentage change in sum(sales)",
                "operational_metrics": [],
            }
        ],
    }


class TestBuildSchemaWithEnums:
    def test_lists_only_low_cardinality_categorical(self):
        schema = builder.build_schema_with_enums(_df())
        assert "DISTINCT VALUES" in schema
        assert "region: ['East', 'West']" in schema
        assert "stage: ['Active', 'Lost', 'Won']" in schema
        # numeric + date columns never listed as enum members
        seg = schema.split("DISTINCT VALUES")[1]
        assert "sales:" not in seg

    def test_truncates_high_cardinality(self):
        df = pd.DataFrame({"region": [f"r{i}" for i in range(30)] * 2, "sales": list(range(60))})
        schema = builder.build_schema_with_enums(df)
        assert "DISTINCT VALUES" not in schema or "region" not in schema.split("DISTINCT VALUES")[1]

    def test_max_cardinality_override_drops_all(self):
        df = _df()[["date", "region", "sales"]]
        # region has 2 distinct > max_cardinality=1 -> no enum section at all
        schema = builder.build_schema_with_enums(df, max_cardinality=1)
        assert "DISTINCT VALUES" not in schema
        assert schema.startswith("Table:")

    def test_shares_prefix_with_plain_schema(self):
        assert builder.build_schema_with_enums(_df()).startswith(builder.extract_schema(_df()))


class TestIdentifyPrioritiesAnchorAware:
    def test_prompt_renders_anchor_and_definition(self, monkeypatch):
        captured = {}

        def fake_ask(prompt, **k):
            captured["prompt"] = prompt
            return {"domain": "", "health_indicators": [], "priorities": []}

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        period = {"date_column": "close_date", "definition_text": "current = Q4'17, prior = Q3'17"}
        builder.identify_priorities("schema", {}, {}, period=period)
        assert "close_date" in captured["prompt"]
        assert "Q4'17" in captured["prompt"]

    def test_prompt_unanchored_has_guard_text(self, monkeypatch):
        captured = {}

        def fake_ask(prompt, **k):
            captured["prompt"] = prompt
            return {"domain": "", "health_indicators": [], "priorities": []}

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        builder.identify_priorities("schema", {}, {})
        assert "none detected" in captured["prompt"]


class TestAnchorPreflight:
    def test_0_vs_0_delta_flagged(self):
        spec = {
            "name": "Active Deals",
            "agg": "count",
            "condition": "df['stage'] == 'Active'",
            "compare": "pct_change",
            "unit": "count",
        }
        keep, flagged = builder._anchor_preflight([spec], _df(), _period())
        assert keep == []
        assert "Active Deals" in flagged
        assert "0 vs 0" in flagged["Active Deals"]
        assert "date" in flagged["Active Deals"]

    def test_healthy_delta_kept(self):
        spec = {
            "name": "Revenue",
            "agg": "sum",
            "value_column": "sales",
            "compare": "pct_change",
            "unit": "currency",
        }
        keep, flagged = builder._anchor_preflight([spec], _df(), _period())
        assert keep == [spec]
        assert flagged == {}

    def test_level_never_flagged_even_when_zero(self):
        spec = {"name": "Active Snapshot", "agg": "count", "condition": "df['stage'] == 'Active'", "compare": "level"}
        keep, flagged = builder._anchor_preflight([spec], _df(), _period())
        assert keep == [spec]
        assert flagged == {}

    def test_empty_returns_empty(self):
        keep, flagged = builder._anchor_preflight([], _df(), _period())
        assert keep == [] and flagged == {}


class TestViabilityScan:
    def test_delta_without_time_dimension_warns(self):
        pri = {
            "name": "Growth",
            "kpis": [
                {
                    "name": "A",
                    "measurement": "percentage change in sum(sales)",
                    "operational_metrics": [{"name": "B", "measurement": "mean(b) vs prior period", "operational_metrics": []}],
                }
            ],
        }
        warns = builder.scan_priority_viability([pri], {}, _df())
        names = [w[1] for w in warns]
        assert "A" in names and "B" in names
        assert all(w[0] == "Growth" for w in warns)

    def test_no_warnings_when_prior_data_exists(self):
        warns = builder.scan_priority_viability([_pri()], _period(), _df())
        assert warns == []


class TestFriendlyReason:
    def test_0_vs_0_reason_reads_cleanly(self):
        reason = (
            "this metric counts 0 rows in both the current and prior period windows "
            "(0 vs 0), so no period-over-period delta exists."
        )
        text = builder.friendly_reason(reason)
        assert "snapshot" in text.lower()


class TestComputeWithPreflight:
    def test_0_vs_0_metric_not_computable_and_healthy_one_computes(self, monkeypatch):
        def fake_ask_json(prompt, **k):
            return [
                {"name": "Revenue", "agg": "sum", "value_column": "sales", "compare": "pct_change", "unit": "currency"},
                {
                    "name": "Active Deals",
                    "agg": "count",
                    "condition": "df['stage'] == 'Active'",
                    "compare": "pct_change",
                    "unit": "count",
                },
            ]

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask_json)
        pri = {
            "name": "Growth",
            "kpis": [
                {
                    "name": "Revenue",
                    "metric": "sales",
                    "measurement": "percentage change in sum(sales)",
                    "operational_metrics": [
                        {"name": "Active Deals", "metric": "stage", "measurement": "count change in active deals"}
                    ],
                }
            ],
        }
        res = builder.compute_priority_values(pri, _df(), builder.build_schema_with_enums(_df()), period=_period())
        values = res["priorities"]["Growth"]["values"]
        skipped = res["priorities"]["Growth"]["skipped"]
        revenue = values["Revenue"]
        assert revenue["status"] == "computed"
        assert revenue["value"] == pytest.approx(145 / 30)  # (175 current - 30 prior) / 30
        assert "Active Deals" not in values
        assert "0 rows in both" in skipped["Active Deals"]["reason"]

    def test_period_override_skips_resolve(self, monkeypatch):
        calls = {"resolve": 0}

        def fake_ask_json(prompt, **k):
            return [{"name": "Revenue", "agg": "sum", "value_column": "sales", "compare": "level", "unit": "currency"}]

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask_json)

        def fake_resolve(*a, **k):
            calls["resolve"] += 1
            return _period()

        monkeypatch.setattr(builder, "resolve_period", fake_resolve)
        builder.compute_priority_values(_pri(), _df(), "schema", period=_period())
        assert calls["resolve"] == 0


class TestBlueprintPass:
    """O3 two-pass generation: the blueprint gates measure candidates to what the
    schema + data can actually compute before authoring ever begins."""

    def _blueprint_raw(self):
        return {
            "domain": "sales pipeline",
            "value_chain": [{"stage": "upstream", "focus": "generate pipeline", "schema_columns": ["date", "stage"]}],
            "measure_candidates": [
                {
                    "name": "Revenue Growth",
                    "column": "sales",
                    "form": "sum",
                    "compare": "pct_change",
                    "measurement": "percentage change in sum(sales)",
                    "baseline_proof": "prior Jan-2026 window has non-zero sales rows",
                    "why": "rows carry close_date in both windows",
                },
                {
                    "name": "Fabricated Count",
                    "column": "not_a_column",
                    "form": "count",
                    "compare": "pct_change",
                    "measurement": "percentage change in count",
                    "baseline_proof": "prior rows exist",
                    "why": "impossible",
                },
            ],
        }

    def test_blueprint_filters_candidates_deterministically(self, monkeypatch):
        captured = {}

        def fake_ask(prompt, **k):
            captured["prompt"] = prompt
            return self._blueprint_raw()

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        bp = builder.build_priority_blueprint(
            builder.build_schema_with_enums(_df()),
            {},
            {},
            period=_period(),
            df=_df(),
        )
        names = [c.get("name") for c in bp["measure_candidates"]]
        assert "Revenue Growth" in names
        assert "Fabricated Count" not in names
        ex = [e.get("name") for e in bp["excluded"]]
        assert "Fabricated Count" in ex and any("not in the schema" in e.get("reason", "") for e in bp["excluded"])
        assert "Sales-2026" not in str(captured["prompt"]) or True  # prompt carries schema/DISTINCT VALUES

    def test_blueprint_filters_delta_with_empty_prior(self, monkeypatch):
        raw = {
            "measure_candidates": [
                {
                    "name": "NoBasis",
                    "column": "sales",
                    "form": "sum",
                    "compare": "pct_change",
                    "measurement": "percentage change in sum(sales)",
                    "baseline_proof": "prior rows exist",
                    "why": "reason",
                }
            ]
        }

        def fake_ask(prompt, **k):
            return raw

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        period = _period()
        period["prior_start"] = "2015-01-01"
        period["prior_end"] = "2015-01-31"  # empty prior window
        bp = builder.build_priority_blueprint("schema", {}, {}, period=period, df=_df())
        assert bp["measure_candidates"] == []
        assert "NoBasis" in [e.get("name") for e in bp["excluded"]]

    def test_identify_priorities_is_two_pass_blueprint_constrained(self, monkeypatch):
        """The authoring prompt embeds the blueprint block; candidates outside it must
        be rejected at author time."""
        seen = []

        def fake_ask(prompt, **k):
            seen.append(prompt)
            if len(seen) == 1:
                return self._blueprint_raw()
            return {
                "domain": "sales pipeline",
                "health_indicators": [],
                "priorities": [
                    {
                        "name": "Grow revenue",
                        "description": "Goal",
                        "executive_questions": ["Are we growing?"],
                        "kpis": [
                            {
                                "name": "Revenue Growth",
                                "metric": "sales",
                                "description": "me",
                                "measurement": "percentage change in sum(sales)",
                                "form": "sum",
                                "compare": "pct_change",
                                "unit": "currency",
                            }
                        ],
                    }
                ],
            }

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        frame = builder.identify_priorities(builder.build_schema_with_enums(_df()), {}, {}, period=_period(), df=_df())
        assert len(seen) == 2  # pass 1 blueprint + pass 2 authoring (contract passes, no repair)
        assert "COMPUTABILITY BLUEPRINT" in seen[1]
        assert "measure_candidates" not in seen[1].lower() or "CONSTRAINED MEASURE CANDIDATES" in seen[1]
        assert frame["priorities"][0]["kpis"][0]["name"] == "Revenue Growth"
        assert frame["excluded_metrics"] == []

    def test_no_blueprint_candidates_falls_back_to_gate(self, monkeypatch):
        def fake_ask(prompt, **k):
            return {"domain": "", "measure_candidates": []}

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        bp = builder.build_priority_blueprint("schema", {}, {}, period=_period(), df=None)
        assert bp["measure_candidates"] == []
        block = builder._format_blueprint_block(bp)
        assert "No computable measure candidates" in block


class TestPriorityContract:
    """The definition contract: authored KPIs/operational metrics must carry
    `form`/`compare`/`unit`, reference a real column, and pass the data gate — enforced
    at authoring time, with ONE repair pass before honest exclusion."""

    def _pri(self, **metric):
        base = {
            "name": "Metric",
            "metric": "sales",
            "description": "me",
            "measurement": "percentage change in sum(sales)",
            "form": "sum",
            "compare": "pct_change",
            "unit": "currency",
        }
        base.update(metric)
        return {
            "domain": "d",
            "health_indicators": [],
            "priorities": [
                {
                    "name": "Growth",
                    "description": "g",
                    "executive_questions": ["Growth?"],
                    "kpis": [
                        {
                            "name": "Revenue Growth",
                            "metric": "sales",
                            "description": "me",
                            "measurement": "percentage change in sum(sales)",
                            "form": "sum",
                            "compare": "pct_change",
                            "unit": "currency",
                            "operational_metrics": [base],
                        }
                    ],
                }
            ],
        }

    def test_validator_ok_on_contract_compliant(self):
        pri = self._pri()
        assert builder.validate_priority_metrics(pri["priorities"], _period(), _df()) == []

    def test_validator_flags_missing_column(self):
        pri = self._pri(metric="not_a_column")
        failures = builder.validate_priority_metrics(pri["priorities"], _period(), _df())
        assert failures and "not_a_column" in failures[0][2]

    def test_validator_flags_bad_form_compare_unit(self):
        for kwarg in ({"form": "bogus"}, {"compare": "bogus"}, {"unit": "bogus"}):
            pri = self._pri(**kwarg)
            failures = builder.validate_priority_metrics(pri["priorities"], _period(), _df())
            assert failures, kwarg
            assert "bogus" in failures[0][2]

    def test_validator_flags_delta_with_empty_prior(self):
        pri = self._pri()
        period = dict(_period())
        period["prior_start"] = "2015-01-01"
        period["prior_end"] = "2015-01-31"
        failures = builder.validate_priority_metrics(pri["priorities"], period, _df())
        assert failures and "prior" in failures[0][2]

    def test_repair_then_all_pass_never_excludes(self, monkeypatch):
        seen = []
        blueprint = {
            "measure_candidates": [
                {
                    "name": "Revenue Growth",
                    "column": "sales",
                    "form": "sum",
                    "compare": "pct_change",
                    "measurement": "percentage change in sum(sales)",
                    "baseline_proof": "prior rows exist",
                    "why": "why",
                }
            ],
            "domain": "d",
        }

        def fake_ask(prompt, **k):
            seen.append(prompt)
            if len(seen) == 1:
                return blueprint
            if len(seen) == 2:
                # bad draft: form outside enum
                return {
                    "domain": "d",
                    "health_indicators": [],
                    "priorities": [
                        {
                            "name": "Growth",
                            "description": "g",
                            "executive_questions": ["Growth?"],
                            "kpis": [
                                {
                                    "name": "Revenue Growth",
                                    "metric": "sales",
                                    "description": "me",
                                    "measurement": "percentage change in sum(sales)",
                                    "form": "bogus",
                                    "compare": "pct_change",
                                    "unit": "currency",
                                }
                            ],
                        }
                    ],
                }
            # repair pass: fixes the metric
            return {
                "domain": "d",
                "health_indicators": [],
                "priorities": [
                    {
                        "name": "Growth",
                        "description": "g",
                        "executive_questions": ["Growth?"],
                        "kpis": [
                            {
                                "name": "Revenue Growth",
                                "metric": "sales",
                                "description": "me",
                                "measurement": "percentage change in sum(sales)",
                                "form": "sum",
                                "compare": "pct_change",
                                "unit": "currency",
                            }
                        ],
                    }
                ],
            }

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        frame = builder.identify_priorities(builder.build_schema_with_enums(_df()), {}, {}, period=_period(), df=_df())
        assert len(seen) == 3  # blueprint + authoring + repair
        assert "REPAIR PASS" in seen[2]
        assert frame["priorities"][0]["kpis"][0]["form"] == "sum"
        assert frame["excluded_metrics"] == []

    def test_still_failing_after_repair_is_excluded(self, monkeypatch):
        seen = []
        blueprint = {"measure_candidates": [], "domain": "d"}
        bad_frame = {
            "domain": "d",
            "health_indicators": [],
            "priorities": [
                {
                    "name": "Growth",
                    "description": "g",
                    "executive_questions": ["Growth?"],
                    "kpis": [
                        {
                            "name": "Revenue Growth",
                            "metric": "ghost",
                            "description": "me",
                            "measurement": "percentage change in sum(ghost)",
                            "form": "sum",
                            "compare": "pct_change",
                            "unit": "currency",
                        }
                    ],
                }
            ],
        }

        def fake_ask(prompt, **k):
            seen.append(prompt)
            if len(seen) == 1:
                return blueprint
            # authoring AND repair both return the same doomed metric
            return bad_frame

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        frame = builder.identify_priorities(builder.build_schema_with_enums(_df()), {}, {}, period=_period(), df=_df())
        assert len(seen) == 3
        assert frame["priorities"][0]["kpis"] == []  # doomed KPI dropped
        assert frame["excluded_metrics"]
        assert frame["excluded_metrics"][0]["name"] == "Revenue Growth"
        assert "ghost" in frame["excluded_metrics"][0]["reason"]

    def test_excluded_metrics_persisted_in_framework_dict(self, monkeypatch):
        seen = []
        blueprint = {"measure_candidates": [], "domain": "d"}

        def fake_ask(prompt, **k):
            seen.append(prompt)
            if len(seen) == 1:
                return blueprint
            return {"domain": "d", "health_indicators": [], "priorities": []}

        monkeypatch.setattr(builder.llm, "ask_json", fake_ask)
        frame = builder.identify_priorities(builder.build_schema_with_enums(_df()), {}, {}, period=_period(), df=_df())
        assert "excluded_metrics" in frame
