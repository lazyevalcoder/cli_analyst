"""Priority dimension breakdowns: LLM-suggested dimension + deterministic per-member
metric matrix (metrics in rows, members in columns), persisted with priority values and
fed to interpret. Guards against: fabricated dimensions, per-member value substitution,
and interpret hallucinating members."""

import pandas as pd
import pytest

from src.analyst import builder


def _df():
    """8 rows: 4 current (Aug 2026), 4 prior (Jan-Feb 2026)."""
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
            "region": ["West", "West", "East", "East", "West", "East", "West", "East"],
            "segment": ["Corp", "SMB", "Corp", "SMB", "SMB", "Corp", "Corp", "SMB"],
            "sales": [100, 200, 300, 400, 10, 20, 30, 40],
        }
    )


def _sparse_df():
    """West has rows ONLY in the current period; East only in the prior."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01", "2026-08-02", "2026-01-15"]),
            "region": ["West", "West", "East"],
            "sales": [10, 20, 5],
        }
    )


def _big_df():
    """60 rows with a per-row id column (high cardinality) + a region column."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                [f"2026-08-{i % 28 + 1:02d}" for i in range(30)] + [f"2026-01-{i % 28 + 1:02d}" for i in range(30)]
            ),
            "id_col": [f"id{i}" for i in range(60)],
            "region": ["West"] * 30 + ["East"] * 30,
            "sales": list(range(60)),
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
    }


def _pri():
    return {
        "name": "Growth",
        "description": "Drive revenue growth",
        "executive_questions": ["Where is growth?"],
        "kpis": [
            {"name": "Revenue", "metric": "sales", "measurement": "percentage change in sum(sales)", "operational_metrics": []}
        ],
    }


def _values():
    spec = {"name": "Revenue", "agg": "sum", "value_column": "sales", "compare": "pct_change", "unit": "percent"}
    return {"Revenue": {"status": "computed", "value": 8.5, "unit": "percent", "basis": "current 1000 vs prior 100", "spec": spec}}


class TestDimensionCandidates:
    def test_includes_categorical_low_cardinality(self):
        cands = builder._categorical_dimension_candidates(_df(), _period())
        cols = [c["column"] for c in cands]
        assert "region" in cols and "segment" in cols

    def test_excludes_numeric_and_date_column(self):
        cands = builder._categorical_dimension_candidates(_df(), _period())
        cols = [c["column"] for c in cands]
        assert "sales" not in cols and "date" not in cols

    def test_excludes_high_cardinality(self):
        cands = builder._categorical_dimension_candidates(_big_df(), _period())
        cols = [c["column"] for c in cands]
        assert "id_col" not in cols
        assert "region" in cols

    def test_sorted_by_coverage_then_cardinality(self):
        cands = builder._categorical_dimension_candidates(_df(), _period())
        coverages = [c["coverage"] for c in cands]
        assert coverages == sorted(coverages, reverse=True)


class TestSuggestDimension:
    def test_valid_llm_pick_used(self, monkeypatch):
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: {"column": "segment", "rationale": "targeting"})
        dim = builder.suggest_breakdown_dimensions(_pri(), _df(), "schema", _period())
        assert dim["column"] == "segment"
        assert dim["rationale"] == "targeting"

    def test_invalid_pick_falls_back_to_top_candidate(self, monkeypatch):
        # "sales" is numeric — not a valid candidate; must fall back deterministically.
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: {"column": "sales", "rationale": "bad"})
        dim = builder.suggest_breakdown_dimensions(_pri(), _df(), "schema", _period())
        assert dim["column"] == "region"

    def test_absent_pick_falls_back(self, monkeypatch):
        monkeypatch.setattr(builder.llm, "ask_json", lambda *a, **k: None)
        dim = builder.suggest_breakdown_dimensions(_pri(), _df(), "schema", _period())
        assert dim["column"] == "region"

    def test_no_candidates_returns_none(self):
        # Only numeric/date columns -> no dimension is suggested, honestly.
        df = _df()[["date", "sales"]]
        assert builder.suggest_breakdown_dimensions(_pri(), df, "schema", _period()) is None


class TestComputeBreakdowns:
    def test_per_member_values_hand_computed(self):
        dim = {"column": "region", "members": ["West", "East"]}
        b = builder.compute_priority_breakdowns(_pri(), _df(), _values(), _period(), dim)
        by = {c["member"]: c for c in b["region"]["Revenue"]}
        assert by["West"]["status"] == "computed"
        assert by["West"]["current"] == pytest.approx(300)
        assert by["West"]["prior"] == pytest.approx(40)
        assert by["West"]["delta"] == pytest.approx(6.5)  # (300-40)/40
        assert by["East"]["delta"] == pytest.approx(10.66666, abs=1e-4)  # (700-60)/60
        assert by["West"]["verified"] is True

    def test_second_dimension_matrix(self):
        dim = {"column": "segment", "members": ["Corp", "SMB"]}
        b = builder.compute_priority_breakdowns(_pri(), _df(), _values(), _period(), dim)
        by = {c["member"]: c for c in b["segment"]["Revenue"]}
        assert by["Corp"]["delta"] == pytest.approx(7.0)  # (400-50)/50
        assert by["SMB"]["delta"] == pytest.approx(11.0)  # (600-50)/50

    def test_member_without_prior_rows_is_honest_not_computable(self):
        dim = {"column": "region", "members": ["West", "East"]}
        b = builder.compute_priority_breakdowns(_pri(), _sparse_df(), _values(), _period(), dim)
        by = {c["member"]: c for c in b["region"]["Revenue"]}
        assert by["West"]["status"] == "not_computable"
        assert by["West"]["delta"] is None
        assert "prior period" in by["West"]["reason_display"]
        assert by["East"]["status"] == "not_computable"
        assert "current period" in by["East"]["reason_display"]

    def test_skips_not_computable_metrics_and_missing_spec(self):
        values = {"Bad": {"status": "not_computable", "value": None}, "NoSpec": {"status": "computed", "value": 1.0}}
        dim = {"column": "region", "members": ["West", "East"]}
        b = builder.compute_priority_breakdowns(_pri(), _df(), values, _period(), dim)
        assert b == {}

    def test_dimension_members_sorted(self):
        assert builder._dimension_members(_df(), "region") == ["East", "West"]


class TestInterpretUsesBreakdowns:
    def test_breakdowns_injected_into_prompt(self, monkeypatch):
        captured = {}

        def fake_ask(prompt, **k):
            captured["prompt"] = prompt
            return "summary"

        monkeypatch.setattr(builder.llm, "ask", fake_ask)
        out = builder.interpret_priority(_pri(), _values(), {"region": [{"member": "West", "delta": 6.5}]})
        assert out == "summary"
        assert '"member": "West"' in captured["prompt"]

    def test_interpret_works_without_breakdowns(self, monkeypatch):
        monkeypatch.setattr(builder.llm, "ask", lambda *a, **k: "summary")
        assert builder.interpret_priority(_pri(), _values()) == "summary"


class TestDegenerateBreakdownsSkipped:
    """Regression: a metric structurally bound to the breakdown dimension (condition
    selecting one of its members, or a group-by share on it) collapses to 1.0/0.0 cells —
    the all-zero rows the user saw for "Express Ship Mode Volume Share" and "Corporate
    Segment Profit Share Change". Its per-member cells must be skipped entirely."""

    def _locked_values(self):
        spec = {
            "name": "Corporate Share",
            "agg": "share",
            "numerator": {"agg": "sum", "value_column": "sales", "condition": "df['segment'] == 'Corp'"},
            "denominator": {"agg": "sum", "value_column": "sales"},
            "compare": "pp_change",
            "unit": "ratio",
        }
        return {
            "Corporate Share": {
                "status": "computed",
                "value": -0.05,
                "unit": "ratio",
                "basis": "cur 0.5 vs pri 0.55",
                "spec": spec,
            }
        }

    def test_condition_locked_spec_is_degenerate(self):
        spec = self._locked_values()["Corporate Share"]["spec"]
        assert builder._breakdown_degenerate_for_dim(spec, "segment") is True
        assert builder._breakdown_degenerate_for_dim(spec, "region") is False

    def test_group_share_and_topk_share_degenerate(self):
        group_share = {
            "steps": [{"op": "group", "group_by": "segment", "inner_agg": "share", "value": "sales", "outer_agg": "max"}]
        }
        topk = {"agg": "topk_share", "group_by": "segment", "k": 1}
        assert builder._breakdown_degenerate_for_dim(group_share, "segment") is True
        assert builder._breakdown_degenerate_for_dim(topk, "segment") is True

    def test_unrelated_condition_not_degenerate(self):
        # High-Margin share style: condition on a different column -> meaningful cells.
        spec = {
            "agg": "share",
            "value_column": "sales",
            "condition": "df['margin'] > 0.5",
        }
        assert builder._breakdown_degenerate_for_dim(spec, "segment") is False

    def test_locked_metric_row_omitted_from_matrix(self):
        dim = {"column": "segment", "members": ["Corp", "SMB"]}
        values = {"Revenue": _values()["Revenue"], **self._locked_values()}
        b = builder.compute_priority_breakdowns(_pri(), _df(), values, _period(), dim)
        assert "Revenue" in b["segment"]
        assert "Corporate Share" not in b["segment"]


class TestInterpretCleaner:
    """Regression: interpret responses leaked the model's chain-of-thought into the
    stored interpretation_summary (prompt echo, sentence counting, output-generation
    doodads). The cleaner must keep only the final narrative answer."""

    def test_clean_text_passes_through(self):
        text = "The priority is on track. Sales grew 12%, led by the West region. Executives should keep investing."
        assert builder._clean_interpretation(text) == text

    def test_reasoning_scaffold_is_stripped_to_final_answer(self):
        text = (
            "- **OFF RULE:** flag KPIs below threshold.\n"
            "   - Structure Requirements:\n"
            "     - OPEN: verdict with north-star KPI.\n"
            "Let's count sentences: 5. Fits the 3-6 constraint.\n"
            "   Draft: The priority is off track, as Q4 shows mix declining.\n"
            "   *(Self-Correction)*: keep it tight.\n"
            "\n"
            "response\n"
            "\n"
            "The priority is off track, as Q4-2013 data shows our high-margin share fell 14.4 points. "
            "All metrics are verified and computed. Executives must immediately rebalance pricing now."
        )
        out = builder._clean_interpretation(text)
        assert "**" not in out
        assert "\u2705" not in out
        assert "response" not in out
        assert out.startswith("The priority is off track, as Q4-2013")

    def test_looks_like_reasoning_flags_polluted_only(self):
        assert builder._looks_like_reasoning("Let's draft carefully. Count: 5. ✅") is True
        assert builder._looks_like_reasoning("The priority is on track. Growth is healthy.") is False


class TestShellPersistence:
    def test_ensure_priority_values_persists_breakdowns(self, monkeypatch):
        from src.analyst.shell import AnalystShell

        class _FakeProject:
            def __init__(self):
                self.priority_values = {}

            def save(self):
                pass

        shell = AnalystShell.__new__(AnalystShell)
        shell.project = _FakeProject()
        shell.df = _df()

        def fake_compute(*a, **k):
            return {
                "generated_at": "t",
                "data_fingerprint": "fp",
                "engine_version": builder.COMPUTE_ENGINE_VERSION,
                "period_definition": "cur vs pri",
                "period": _period(),
                "priorities": {"Growth": {"priority_ref": "Growth", "fingerprint": "f", "values": _values()}},
            }

        monkeypatch.setattr(builder, "compute_priority_values", fake_compute)
        monkeypatch.setattr(builder, "suggest_breakdown_dimensions", lambda *a, **k: {"column": "region", "rationale": "test"})
        rec = shell._ensure_priority_values(_pri())
        stored = shell.project.priority_values["priorities"]["Growth"]
        assert stored.get("breakdown_dimensions") == [{"column": "region", "rationale": "test", "members": ["East", "West"]}]
        assert "region" in stored.get("breakdowns", {})
        assert rec is stored or rec == stored

    def test_current_record_gets_breakdowns_without_recompute(self, monkeypatch):
        # A record that is already current (engine/fingerprint/data match) must NOT
        # recompute scalars but MUST gain its breakdown matrix on the next ensure.
        from src.analyst.shell import AnalystShell

        class _FakeProject:
            def __init__(self, pv):
                self.priority_values = pv

            def save(self):
                pass

        shell = AnalystShell.__new__(AnalystShell)
        shell.df = _df()
        stored = {
            "engine_version": builder.COMPUTE_ENGINE_VERSION,
            "data_fingerprint": builder.data_fingerprint(_df()),
            "period": _period(),
            "priorities": {
                "Growth": {
                    "priority_ref": "Growth",
                    "fingerprint": builder.priority_fingerprint(_pri()),
                    "engine_version": builder.COMPUTE_ENGINE_VERSION,
                    "values": _values(),
                }
            },
        }
        shell.project = _FakeProject(stored)
        monkeypatch.setattr(builder, "suggest_breakdown_dimensions", lambda *a, **k: {"column": "region", "rationale": "test"})
        rec = shell._ensure_priority_values(_pri())
        assert rec.get("breakdowns", {}).get("region")
        assert rec["values"]["Revenue"]["value"] == _values()["Revenue"]["value"]
