"""Reusable table operations. Every result can feed another tool."""

import ast
import operator
from typing import Literal

import pandas as pd
from pydantic import Field, model_validator

from backend.app.analysis import AnalysisError
from backend.app.tools.registry import ToolArgs, ToolContext, tool
from backend.app.tools.result import ToolResult, attributes, dataset_result
from backend.app.tools.validation import check_columns, check_numeric, check_output

Scalar = str | int | float | bool | None


class SourceArgs(ToolArgs):
    source: str = Field(description="Named dataset or a previous dataset result_id.")


class FilterArgs(SourceArgs):
    column: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "is_null", "not_null"] = "eq"
    value: Scalar | list[Scalar] = None


@tool(FilterArgs, description="""
Keep rows matching a column condition. Chain filters for AND conditions; in/not_in take a list.
contains matches literal text, case-insensitively. Null checks need no value. Keeps geometry and does not change the map.
""")
def filter_rows(args: FilterArgs, ctx: ToolContext) -> ToolResult:
    frame = ctx.get_frame(args.source)
    check_columns(frame, [args.column])
    column = frame[args.column]
    if args.op in ("is_null", "not_null"):
        mask = column.isna() if args.op == "is_null" else column.notna()
    elif args.op in ("in", "not_in"):
        if not isinstance(args.value, list):
            raise AnalysisError("invalid_filter", "in/not_in requires a list of values.",
                                'For example: value=["C01", "C02"].')
        mask = column.isin(args.value)
        if args.op == "not_in":
            mask = ~mask
    elif args.op == "contains":
        if not isinstance(args.value, str):
            raise AnalysisError("invalid_filter", "contains requires text.", "Pass a string value.")
        mask = column.astype("string").str.contains(args.value, case=False, regex=False, na=False)
    else:
        if args.value is None or isinstance(args.value, list):
            raise AnalysisError("invalid_filter", "This comparison requires a single non-null value.",
                                "Use is_null/not_null for missing values or in/not_in for lists.")
        comparisons = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt,
                       "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
        try:
            mask = comparisons[args.op](column, args.value) & column.notna()
        except TypeError:
            raise AnalysisError("invalid_filter", "The value cannot be compared with this column.",
                                "Use a value of the column's type from the dataset schema.") from None
    out = frame.loc[mask.fillna(False)].reset_index(drop=True)
    return dataset_result(f"Kept {len(out)} of {len(frame)} row(s).", out)


class DistinctArgs(SourceArgs):
    columns: list[str] = Field(min_length=1, description="Keys defining a distinct row, e.g. ['site_id'].")


@tool(DistinctArgs, description="""
Keep the first row for each distinct combination of key columns; preserves other columns and geometry.
After matching sites to overlapping polygons, deduplicate by site_id before counting or summing TIV.
""")
def distinct_rows(args: DistinctArgs, ctx: ToolContext) -> ToolResult:
    frame = ctx.get_frame(args.source)
    check_columns(frame, args.columns)
    out = frame.drop_duplicates(subset=args.columns, ignore_index=True)
    return dataset_result(f"{len(out)} distinct row(s) from {len(frame)} input row(s).", out)


class Measure(ToolArgs):
    function: Literal["count", "count_distinct", "sum"]
    column: str | None = Field(None, description="Required for sum/count_distinct. Omit for count of rows.")
    output: str = Field(min_length=1, description="Output column name, e.g. n_sites or exposed_tiv_eur.")

    @model_validator(mode="after")
    def needs_column(self):
        if self.function != "count" and self.column is None:
            raise ValueError("sum/count_distinct requires column")
        return self


class AggregateArgs(SourceArgs):
    group_by: list[str] = Field(default_factory=list, description="Grouping columns; empty means a single total.")
    measures: list[Measure] = Field(min_length=1, description="Counts or sums, each with its own output name.")


@tool(AggregateArgs, description="""
Count rows, count distinct values or sum numeric columns, optionally grouped by columns.
Name each measure's output. Returns a reusable table. Sum of an empty input is zero; ungrouped count is zero.
Deduplicate sites before summing TIV if spatial matches repeated them.
""")
def aggregate(args: AggregateArgs, ctx: ToolContext) -> ToolResult:
    frame = attributes(ctx.get_frame(args.source)).reset_index(drop=True)
    check_columns(frame, args.group_by)
    names = [measure.output for measure in args.measures]
    if len(set(names)) != len(names) or set(names) & set(args.group_by):
        raise AnalysisError("invalid_output_column", "Measure output names must be unique and not grouping keys.",
                            "Give each measure a different output name.")
    aggregations = {}
    for measure in args.measures:
        if measure.column is not None:
            check_columns(frame, [measure.column])
        if measure.function == "sum":
            check_numeric(frame, [measure.column])
        function = {"count": "count" if measure.column else "size",
                    "count_distinct": "nunique", "sum": "sum"}[measure.function]
        aggregations[measure.output] = (measure.column or frame.columns[0], function)
    if args.group_by:
        out = frame.groupby(args.group_by, as_index=False, dropna=False, sort=True).agg(**aggregations)
    else:
        out = pd.DataFrame([{name: len(frame) if function == "size" else frame[column].agg(function)
                             for name, (column, function) in aggregations.items()}])
    return dataset_result(f"Aggregated {len(frame)} row(s) into {len(out)} row(s).", out,
                          {"group_by": args.group_by, "input_rows": len(frame)})


class JoinArgs(ToolArgs):
    left: str = Field(description="Left dataset or result_id; its geometry, if any, is retained.")
    right: str = Field(description="Right dataset or result_id; adds non-geometry columns.")
    on: list[str] = Field(min_length=1, description="Shared key columns.")
    how: Literal["inner", "left", "outer"] = "left"
    relationship: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"] = "many_to_one"


@tool(JoinArgs, description="""
Join tables on shared keys. A left join keeps zero-exposure companies when full portfolio totals are on the left.
Right-hand duplicate column names get _right; right geometry is omitted. Default requires unique right keys.
Missing matches remain null: calculate can fill them with zero before arithmetic.
""")
def join_tables(args: JoinArgs, ctx: ToolContext) -> ToolResult:
    left = ctx.get_frame(args.left).reset_index(drop=True)
    right = attributes(ctx.get_frame(args.right)).reset_index(drop=True)
    check_columns(left, args.on)
    check_columns(right, args.on)
    try:
        out = left.merge(right, on=args.on, how=args.how, suffixes=("", "_right"), validate=args.relationship)
    except pd.errors.MergeError:
        raise AnalysisError("invalid_join", "Join keys do not meet the requested uniqueness constraint.",
                            "Aggregate/deduplicate first, or choose an explicit relationship.") from None
    except ValueError as error:
        raise AnalysisError("invalid_join", str(error), "Use compatible key columns from the two schemas.") from None
    return dataset_result(f"Joined {len(left)} and {len(right)} row(s) into {len(out)} row(s).", out)


class CalculateArgs(SourceArgs):
    expression: str = Field(description="Arithmetic on numeric column names and constants: +, -, *, /, parentheses.")
    output_column: str = Field(min_length=1)
    fill_nulls: dict[str, float] = Field(default_factory=dict,
                                      description="Replace missing numeric inputs first, e.g. {'exposed_tiv_eur': 0}.")


def _arithmetic(node: ast.AST, frame: pd.DataFrame):
    if isinstance(node, ast.Name):
        check_numeric(frame, [node.id])
        return frame[node.id]
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _arithmetic(node.operand, frame)
        return value if isinstance(node.op, ast.UAdd) else -value
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    if isinstance(node, ast.BinOp) and type(node.op) in operations:
        left, right = _arithmetic(node.left, frame), _arithmetic(node.right, frame)
        if isinstance(node.op, ast.Div):
            if isinstance(right, pd.Series):
                right = right.astype(float).where(right != 0)
            elif right == 0:
                right = float("nan")
        return operations[type(node.op)](left, right)
    raise AnalysisError("invalid_expression", "Unsupported expression.",
                        "Use column names, numbers, +, -, *, / and parentheses; no code or function calls.")


@tool(CalculateArgs, description="""
Add a column calculated from numeric columns and constants using +, -, *, / and parentheses.
Use fill_nulls for unmatched join values (e.g. zero exposure). Division by zero returns null, never infinity.
Example: expression='exposed_tiv_eur / portfolio_tiv_eur * 100', output_column='exposure_pct'.
""")
def calculate(args: CalculateArgs, ctx: ToolContext) -> ToolResult:
    frame = ctx.get_frame(args.source)
    check_output(frame, args.output_column)
    check_numeric(frame, list(args.fill_nulls))
    for column, value in args.fill_nulls.items():
        frame[column] = frame[column].fillna(value)
    try:
        expression = ast.parse(args.expression, mode="eval").body
    except SyntaxError:
        raise AnalysisError("invalid_expression", "The arithmetic expression is invalid.",
                            "Use numeric column names and +, -, *, / with balanced parentheses.") from None
    value = _arithmetic(expression, frame)
    frame[args.output_column] = pd.Series(value, index=frame.index).replace([float("inf"), -float("inf")], float("nan"))
    return dataset_result(f"Calculated {args.output_column} for {len(frame)} row(s).", frame,
                          {"expression": args.expression, "zero_denominator": "null"})


class SortArgs(SourceArgs):
    columns: list[str] = Field(min_length=1, description="Sort keys in priority order, including tie breakers.")
    descending: bool | list[bool] = Field(False, description="One direction for all keys, or one per key.")
    limit: int | None = Field(None, ge=1, description="Optionally keep the first N rows.")


@tool(SortArgs, description="Order rows by one or more columns, optionally keeping the first N. Nulls sort last; preserves geometry.")
def sort_rows(args: SortArgs, ctx: ToolContext) -> ToolResult:
    frame = ctx.get_frame(args.source)
    check_columns(frame, args.columns)
    if isinstance(args.descending, list):
        if len(args.descending) != len(args.columns):
            raise AnalysisError("invalid_arguments", "Sort directions must match the number of columns.",
                                "Pass one boolean, or one boolean per sort key.")
        ascending = [not direction for direction in args.descending]
    else:
        ascending = not args.descending
    out = frame.sort_values(args.columns, ascending=ascending, kind="stable", na_position="last")
    if args.limit is not None:
        out = out.head(args.limit)
    return dataset_result(f"Sorted {len(frame)} row(s); returned {len(out)}.", out.reset_index(drop=True))
