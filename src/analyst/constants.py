"""Single source of truth for the string literals shared across analyst modules.

Every persisted-JSON key, status value, node type, edge relation, and spec-DSL
operator lives here so a rename in one place can never silently break another
module or the on-disk project files. The string VALUES equal the persisted
formats exactly — this module changes no on-disk format.

Keep additions consistent with the actual JSON written by builder/graph/project.
"""

from __future__ import annotations

# ---- value statuses (value-record `status` field, persisted) ----
STATUS_COMPUTED = "computed"
STATUS_NOT_COMPUTABLE = "not_computable"
STATUS_ERROR = "error"
FINAL_STATUSES = frozenset({STATUS_COMPUTED, STATUS_NOT_COMPUTABLE, STATUS_ERROR})

# ---- metric kinds (priority traversal, prompt briefs) ----
KIND_KPI = "KPI"
KIND_OPERATIONAL = "OPERATIONAL"

# ---- node types (metric catalog / unified knowledge graph) ----
NODE_TYPE_KPI = "kpi"
NODE_TYPE_OPERATIONAL_METRIC = "operational_metric"
NODE_TYPE_SUPPORTING_METRIC = "supporting_metric"  # legacy alias of operational
CATALOG_NODE_TYPES = frozenset({NODE_TYPE_KPI, NODE_TYPE_OPERATIONAL_METRIC, NODE_TYPE_SUPPORTING_METRIC})

# ---- edge relation types (unified knowledge graph) ----
RELATION_INFLUENCES = "INFLUENCES"
RELATION_DERIVED_FROM = "DERIVED_FROM"
RELATION_SUPPORTS = "SUPPORTS"

# ---- metric node source values ----
SOURCE_LLM_GENERATED = "llm-generated"
SOURCE_USER_OVERRIDE = "user-override"
SOURCE_STRUCTURAL_KG = "structural-kg"

# ---- value-record keys (persisted in priority_values.json) ----
VALUE_FILTERS = "filters"
VALUE_VALUE = "value"
VALUE_UNIT = "unit"
VALUE_BASIS = "basis"
VALUE_PERIOD = "period"
VALUE_MEASUREMENT = "measurement"
VALUE_SPEC = "spec"
VALUE_VERIFIED = "verified"
VALUE_STATUS = "status"
VALUE_REASON = "reason"
VALUE_REASON_DISPLAY = "reason_display"
VALUE_MISSING_PRIMITIVE = "missing_primitive"
VALUE_SOURCE = "source"

# ---- period-record keys (persisted in priority_values.json `period`) ----
PERIOD_DATE_COLUMN = "date_column"
PERIOD_UNIT = "period_unit"
PERIOD_CURRENT = "current_period"
PERIOD_PRIOR = "prior_period"
PERIOD_CURRENT_START = "current_start"
PERIOD_CURRENT_END = "current_end"
PERIOD_PRIOR_START = "prior_start"
PERIOD_PRIOR_END = "prior_end"
PERIOD_DEFINITION = "definition_text"
PERIOD_BOUND_KEYS = frozenset(
    {
        PERIOD_CURRENT_START,
        PERIOD_CURRENT_END,
        PERIOD_PRIOR_START,
        PERIOD_PRIOR_END,
    }
)

# ---- result envelope keys (compute_priority_values output, persisted) ----
RESULT_GENERATED_AT = "generated_at"
RESULT_DATA_FINGERPRINT = "data_fingerprint"
RESULT_ENGINE_VERSION = "engine_version"
RESULT_PERIOD_DEFINITION = "period_definition"
RESULT_PERIOD = "period"
RESULT_PRIORITIES = "priorities"
RESULT_PRIORITY_REF = "priority_ref"
RESULT_PRIORITY_FINGERPRINT = "fingerprint"
RESULT_VALUES = "values"
RESULT_BREAKDOWN_DIMENSIONS = "breakdown_dimensions"
RESULT_BREAKDOWNS = "breakdowns"

# ---- dimension breakdown keys (persisted in priority_values.json `breakdowns`) ----
BREAKDOWN_COLUMN = "column"
BREAKDOWN_RATIONALE = "rationale"
BREAKDOWN_MEMBERS = "members"
BREAKDOWN_AT = "member"
BREAKDOWN_CURRENT = "current"
BREAKDOWN_PRIOR = "prior"
BREAKDOWN_DELTA = "delta"

# ---- priority / KPI / metric shape keys (LLM contract, persisted) ----
PRIORITY_NAME = "name"
PRIORITY_DESCRIPTION = "description"
PRIORITY_EXECUTIVE_QUESTIONS = "executive_questions"
PRIORITY_KPIS = "kpis"
PRIORITY_SUPPORTING_METRICS = "supporting_metrics"
PRIORITY_OPERATIONAL_METRICS = "operational_metrics"
PRIORITY_METRIC = "metric"
PRIORITY_MEASUREMENT = "measurement"
PRIORITY_ANALYTICAL_LENSES = "analytical_lenses"
PRIORITY_INFLUENCES = "influences"
PRIORITY_DOMAIN = "domain"
PRIORITY_HEALTH_INDICATORS = "health_indicators"
PRIORITY_QUESTION = "question"

# ---- schema-dict keys (persisted in schema.json) ----
SCHEMA_COLUMNS = "columns"
SCHEMA_ROWS = "rows"
SCHEMA_SAMPLE_ROWS = "sample_rows"
SCHEMA_NAME = "name"
SCHEMA_DTYPE = "dtype"
SCHEMA_KIND = "kind"
SCHEMA_UNIQUE = "unique"
SCHEMA_SAMPLE = "sample"

# ---- knowledge-graph container keys (persisted) ----
KG_NODES = "nodes"
KG_EDGES = "edges"
KG_CHAINS = "chains"
KG_DIMENSIONS_AFFECTING = "dimensions_affecting"
KG_HYPOTHESES = "hypotheses"

# ---- spec DSL vocabulary (metric-spec-v2-composable-operator-dsl.md) ----
SPEC_AGG = "agg"
SPEC_COMPARE = "compare"
SPEC_VALUE_COLUMN = "value_column"
SPEC_UNIT = "unit"
SPEC_KIND = "kind"
SPEC_STEPS = "steps"
SPEC_PREP = "prep"
SPEC_INPUT_REF = "input_ref"
SPEC_NUMERATOR = "numerator"
SPEC_DENOMINATOR = "denominator"
SPEC_CONDITION = "condition"
SPEC_GROUP_BY = "group_by"
SPEC_K = "k"
SPEC_CODE = "code"
SPEC_OP = "op"
SPEC_AS = "as"
SPEC_EXPR = "expr"
SPEC_START = "start"
SPEC_END = "end"
SPEC_COLUMN = "column"
SPEC_OUTER_AGG = "outer_agg"
SPEC_INNER_AGG = "inner_agg"
SPEC_VALUE = "value"

AGGS = frozenset({"count", "sum", "mean", "median", "std", "ratio", "share", "topk_share", "count_distinct"})
COMPARES = frozenset({"level", "pct_change", "pp_change", "rate_ratio"})
INNER_AGGS = frozenset({"count", "sum", "mean", "median", "std", "min", "max", "share"})
OUTER_AGGS = frozenset({"mean", "median", "std", "max", "min", "sum"})
DERIVE_OPS = frozenset({"derive.days_between", "derive.year_of", "derive.month_of", "derive.arithmetic"})
SUB_AGGS = frozenset({"count", "sum", "mean", "count_distinct"})

# Bump when the compute engine changes behavior so stored values are forced to recompute.
COMPUTE_ENGINE_VERSION = "engine-v3-2026-08-02-breakdowns"

# ---- analysis turn keys (persisted in analyses/*/turns.jsonl) ----
TURN_TIMESTAMP = "timestamp"
TURN_QUESTION = "question"
TURN_SUMMARY = "summary"
