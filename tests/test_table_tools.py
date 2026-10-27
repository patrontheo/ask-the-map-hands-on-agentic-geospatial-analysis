import json

import pandas as pd
import pytest

from backend.app.tools.registry import ToolContext, dispatch
from backend.app.tools.result import dataset_result


@pytest.fixture
def ctx(bundle):
    return ToolContext(bundle)


def stored(ctx, frame):
    result = dataset_result("Test input", frame)
    result.result_id = ctx.store.next_id()
    ctx.store.add(result)
    return result.result_id


def run(ctx, name, **args):
    result = dispatch(name, args, ctx)
    assert result.status == "ok", result.error
    assert result.map_actions == []
    json.dumps(result.model_dump(), allow_nan=False)
    return result


@pytest.mark.parametrize("op,value,expected", [
    ("eq", "C01", ["C01"]), ("ne", "C01", ["C02", "C03", "C04"]),
    ("in", ["C01", "C03"], ["C01", "C03"]), ("not_in", ["C01", "C03"], ["C02", "C04"]),
])
def test_attribute_filtering(ctx, op, value, expected):
    result = run(ctx, "filter_rows", source="companies", column="company_id", op=op, value=value)
    assert [row["company_id"] for row in result.table.rows] == expected


def test_numeric_and_text_filters_preserve_source_and_geometry(ctx):
    result = run(ctx, "filter_rows", source="sites", column="tiv_eur", op="gte", value=5_000_000)
    assert [row["site_id"] for row in result.table.rows] == ["S01", "S08", "S10", "S13"]
    assert ctx.get_frame(result.result_id).crs == ctx.bundle.sites.crs
    text = run(ctx, "filter_rows", source="companies", column="company_name", op="contains", value="LOGISTICS")
    assert text.table.rows[0]["company_id"] == "C01"
    assert len(ctx.get_frame("sites")) == 13


def test_null_filter_and_empty_aggregate(ctx):
    source = stored(ctx, pd.DataFrame({"value": [None, 3.0]}))
    assert run(ctx, "filter_rows", source=source, column="value", op="is_null").table.total_rows == 1
    assert run(ctx, "filter_rows", source=source, column="value", op="not_null").table.rows == [{"value": 3.0}]
    empty = run(ctx, "filter_rows", source="sites", column="company_id", value="NONE")
    total = run(ctx, "aggregate", source=empty.result_id, measures=[
        {"function": "count", "output": "n_sites"},
        {"function": "sum", "column": "tiv_eur", "output": "tiv_eur"},
    ])
    assert total.table.rows == [{"n_sites": 0, "tiv_eur": 0}]
    grouped = run(ctx, "aggregate", source=empty.result_id, group_by=["company_id"],
                  measures=[{"function": "count", "output": "n_sites"}])
    assert grouped.table.total_rows == 0


def test_distinct_counts_and_grouping(ctx):
    source = stored(ctx, pd.DataFrame({"company_id": ["C01", "C01", "C02"], "site_id": ["S01", "S01", "S03"],
                                       "tiv_eur": [10, 10, 20]}))
    distinct = run(ctx, "distinct_rows", source=source, columns=["site_id"])
    assert distinct.table.total_rows == 2
    grouped = run(ctx, "aggregate", source=source, group_by=["company_id"], measures=[
        {"function": "count", "output": "rows"},
        {"function": "count_distinct", "column": "site_id", "output": "n_sites"},
    ])
    assert grouped.table.rows == [{"company_id": "C01", "rows": 2, "n_sites": 1},
                                  {"company_id": "C02", "rows": 1, "n_sites": 1}]
    # Named source indices duplicate their ID column names; grouping must still work.
    assert run(ctx, "aggregate", source="sites", group_by=["site_id"],
               measures=[{"function": "count", "output": "rows"}]).table.total_rows == 13


def test_join_null_exposure_and_zero_denominators(ctx):
    left = stored(ctx, pd.DataFrame({"company_id": ["A", "B", "C"], "portfolio_tiv_eur": [100, 50, 0]}))
    right = stored(ctx, pd.DataFrame({"company_id": ["A", "C"], "exposed_tiv_eur": [25, 0]}))
    joined = run(ctx, "join_tables", left=left, right=right, on=["company_id"])
    result = run(ctx, "calculate", source=joined.result_id, output_column="exposure_pct",
                 expression="exposed_tiv_eur / portfolio_tiv_eur * 100", fill_nulls={"exposed_tiv_eur": 0})
    assert [row["exposure_pct"] for row in result.table.rows] == [25.0, 0.0, None]
    assert result.data["schema"]["exposure_pct"]["unit"] == "%"
    assert ctx.get_frame(joined.result_id).exposed_tiv_eur.isna().sum() == 1
    assert result.data["zero_denominator"] == "null"


def test_table_join_preserves_left_geometry(ctx):
    result = run(ctx, "join_tables", left="sites", right="companies", on=["company_id"])
    frame = ctx.get_frame(result.result_id)
    assert frame.crs == ctx.bundle.sites.crs and frame.geometry.equals(ctx.bundle.sites.reset_index(drop=True).geometry)
    assert "company_name_right" in frame


def test_calculate_arithmetic_and_sorting(ctx):
    source = stored(ctx, pd.DataFrame({"key": ["B", "A", "C"], "value": [10, 10, 5]}))
    result = run(ctx, "calculate", source=source, expression="-(value + 2) / 2", output_column="result")
    assert [row["result"] for row in result.table.rows] == [-6, -6, -3.5]
    sorted_result = run(ctx, "sort_rows", source=result.result_id, columns=["value", "key"],
                        descending=[True, False], limit=2)
    assert [row["key"] for row in sorted_result.table.rows] == ["A", "B"]
    zero = run(ctx, "calculate", source=source, expression="1 / 0", output_column="undefined")
    assert all(row["undefined"] is None for row in zero.table.rows)


@pytest.mark.parametrize("expression", ["__import__('os')", "value.sum()", "value ** 2", "[value]", "value +"])
def test_calculate_rejects_code_and_unsupported_expressions(ctx, expression):
    source = stored(ctx, pd.DataFrame({"value": [1]}))
    result = dispatch("calculate", {"source": source, "expression": expression, "output_column": "new"}, ctx)
    assert result.error.code == "invalid_expression" and result.error.hint


@pytest.mark.parametrize("name,args,code", [
    ("filter_rows", {"source": "sites", "column": "missing", "value": 1}, "unknown_column"),
    ("filter_rows", {"source": "sites", "column": "tiv_eur", "op": "gt", "value": "x"}, "invalid_filter"),
    ("filter_rows", {"source": "sites", "column": "site_id", "op": "in", "value": "S01"}, "invalid_filter"),
    ("filter_rows", {"source": "sites", "column": "site_id", "op": "contains", "value": 1}, "invalid_filter"),
    ("aggregate", {"source": "sites", "measures": [{"function": "sum", "column": "company_id", "output": "x"}]},
     "invalid_column_type"),
    ("aggregate", {"source": "sites", "group_by": ["company_id"],
                   "measures": [{"function": "count", "output": "company_id"}]}, "invalid_output_column"),
    ("calculate", {"source": "sites", "expression": "1", "output_column": "geometry"}, "invalid_output_column"),
    ("sort_rows", {"source": "sites", "columns": ["site_id"], "descending": [True, False]}, "invalid_arguments"),
])
def test_operation_errors_have_hints(ctx, name, args, code):
    result = dispatch(name, args, ctx)
    assert result.status == "error" and result.error.code == code and result.error.hint


def test_join_rejects_accidental_many_to_many(ctx):
    source = stored(ctx, pd.DataFrame({"key": [1, 1]}))
    result = dispatch("join_tables", {"left": source, "right": source, "on": ["key"]}, ctx)
    assert result.error.code == "invalid_join"
