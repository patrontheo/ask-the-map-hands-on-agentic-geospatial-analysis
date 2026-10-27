from typing import Any, Literal

import geopandas as gpd
import pandas as pd
from pydantic import BaseModel, Field, PrivateAttr

ID_FIELDS = ("site_id", "company_id", "district_code", "incident_id")


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
    # Intermediate data stays in the session, never in the API or model JSON.
    _frame: pd.DataFrame | None = PrivateAttr(default=None)

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
           map_actions: list[dict] | None = None, frame: pd.DataFrame | None = None) -> "ToolResult":
        result = cls(status="ok", summary=summary, data=data or {}, table=table, map_actions=map_actions or [])
        result._frame = frame
        return result

    @classmethod
    def fail(cls, code: str, message: str, hint: str = "") -> "ToolResult":
        return cls(status="error", summary=message, error=ToolErrorInfo(code=code, message=message, hint=hint))


def dataset_result(summary: str, frame: pd.DataFrame, data: dict | None = None) -> ToolResult:
    """A reusable dataset result: readable table and schema for the model, full frame kept in the session."""
    table = table_from_df(attributes(frame).round({"lon": 5, "lat": 5}), id_field=id_field(frame))
    return ToolResult.ok(summary, data={**(data or {}), **frame_info(frame)}, table=table, frame=frame)


def is_spatial(frame: pd.DataFrame) -> bool:
    return isinstance(frame, gpd.GeoDataFrame)


def attributes(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop(columns=frame.geometry.name) if is_spatial(frame) else frame


def id_field(frame: pd.DataFrame) -> str | None:
    return next((name for name in ID_FIELDS if name in frame and frame[name].is_unique), None)


def column_unit(name: str) -> str | None:
    return next((unit for suffix, unit in (("_eur", "EUR"), ("_ha", "ha"), ("_m2", "m²"),
                                           ("_km2", "km²"), ("_pct", "%")) if name.endswith(suffix)), None)


def frame_info(frame: pd.DataFrame) -> dict:
    schema = {name: {"type": str(dtype), **({"unit": unit} if (unit := column_unit(name)) else {})}
              for name, dtype in frame.dtypes.items()}
    crs = str(frame.crs) if is_spatial(frame) and frame.crs else None
    return {"n_rows": len(frame), "schema": schema, "crs": crs}


def table_from_df(df: pd.DataFrame, id_field: str | None = None) -> Table:
    def col_type(dtype) -> str:
        if pd.api.types.is_integer_dtype(dtype):
            return "integer"
        return "number" if pd.api.types.is_numeric_dtype(dtype) else "string"

    columns = [Column(name=c, type=col_type(df[c].dtype), unit=column_unit(c)) for c in df.columns]
    rows = df.astype(object).where(df.notna(), None).to_dict(orient="records")
    return Table(columns=columns, rows=rows, total_rows=len(df), id_field=id_field)


def eur_m(value: float) -> str:
    return f"EUR {value / 1e6:,.1f}M"


def to_llm_payload(result: ToolResult) -> dict:
    """Model-facing data and tables; private frames, map actions and charts are excluded."""
    payload = {"result_id": result.result_id, "status": result.status, "summary": result.summary}
    if result.status == "error":
        payload["error"] = result.error.model_dump()
        return payload
    payload["data"] = result.data
    if result.table is not None:
        payload["table"] = {"columns": [c.name for c in result.table.columns], "rows": result.table.rows}
    return payload
