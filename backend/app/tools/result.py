from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field


class ToolErrorInfo(BaseModel):
    code: str
    message: str
    hint: str = ""


class Column(BaseModel):
    name: str
    type: Literal["string", "number", "integer"]
    unit: str | None = None


class Table(BaseModel):
    columns: list[Column]
    rows: list[dict[str, Any]]
    total_rows: int
    id_field: str | None = None


class ToolResult(BaseModel):
    result_id: str | None = None
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    status: Literal["ok", "error"]
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    table: Table | None = None
    map_actions: list[dict[str, Any]] = Field(default_factory=list)
    chart: dict[str, Any] | None = None
    error: ToolErrorInfo | None = None

    @classmethod
    def ok(cls, summary: str, data: dict | None = None, table: Table | None = None,
           map_actions: list[dict] | None = None) -> "ToolResult":
        return cls(status="ok", summary=summary, data=data or {}, table=table, map_actions=map_actions or [])

    @classmethod
    def fail(cls, code: str, message: str, hint: str = "") -> "ToolResult":
        return cls(status="error", summary=message, error=ToolErrorInfo(code=code, message=message, hint=hint))


def table_from_df(df: pd.DataFrame, id_field: str | None = None, units: dict[str, str] | None = None) -> Table:
    units = units or {}

    def col_type(dtype) -> str:
        if pd.api.types.is_integer_dtype(dtype):
            return "integer"
        return "number" if pd.api.types.is_numeric_dtype(dtype) else "string"

    columns = [Column(name=c, type=col_type(df[c].dtype), unit=units.get(c)) for c in df.columns]
    rows = df.astype(object).where(df.notna(), None).to_dict(orient="records")
    return Table(columns=columns, rows=rows, total_rows=len(df), id_field=id_field)


def to_llm_payload(result: ToolResult) -> dict:
    """What the model sees: no map actions, no chart, no geometry."""
    payload = {"result_id": result.result_id, "status": result.status, "summary": result.summary}
    if result.status == "error":
        payload["error"] = result.error.model_dump()
        return payload
    payload["data"] = result.data
    if result.table is not None:
        payload["table"] = {"columns": [c.name for c in result.table.columns], "rows": result.table.rows}
    return payload
