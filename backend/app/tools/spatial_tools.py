"""General spatial operations in the bundle's projected CRS."""

from typing import Literal

import geopandas as gpd
from pydantic import Field

from backend.app.analysis import AnalysisError
from backend.app.tools.registry import ToolArgs, ToolContext, tool
from backend.app.tools.result import ToolResult, dataset_result, is_spatial
from backend.app.tools.validation import check_output


def _spatial(source: str, ctx: ToolContext) -> gpd.GeoDataFrame:
    frame = ctx.get_frame(source).reset_index(drop=True)
    if not is_spatial(frame) or frame.crs is None:
        raise AnalysisError("invalid_dataset", f"'{source}' needs geometry and a CRS.",
                            "Use a spatial dataset from describe_data or a previous spatial result.")
    projected = frame.to_crs(ctx.bundle.crs_projected)
    projected.geometry = projected.geometry.make_valid()
    return projected


def _polygons(frame: gpd.GeoDataFrame) -> None:
    present = frame.geometry.area.notna() & ~frame.geometry.is_empty
    if not frame.loc[present].geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise AnalysisError("invalid_geometry", "This operation requires polygon geometries.",
                            "Use commune, incident, building or parcel polygons; sites are points.")


class SpatialJoinArgs(ToolArgs):
    left: str = Field(description="Left dataset or result_id; its geometry is retained.")
    right: str = Field(description="Right spatial dataset or result_id.")
    predicate: Literal["intersects", "covered_by", "within", "contains", "covers"] = "intersects"
    how: Literal["inner", "left"] = "inner"


@tool(SpatialJoinArgs, description="""
Match two spatial datasets using the specified left-to-right predicate, retaining left geometry.
For sites in polygons, covered_by includes boundary sites; within excludes them.
Overlapping right polygons can repeat left rows: use distinct_rows on site_id before counts/TIV sums.
""")
def spatial_join(args: SpatialJoinArgs, ctx: ToolContext) -> ToolResult:
    left, right = _spatial(args.left, ctx), _spatial(args.right, ctx)
    # GeoPandas' temporary right index is not an attribute or a reusable join key.
    left = left.drop(columns="index_right", errors="ignore")
    right = right.drop(columns="index_right", errors="ignore")
    right = right.rename(columns={column: f"{column}_right" for column in right.columns
                                  if column in left and column != right.geometry.name})
    out = gpd.sjoin(left, right, how=args.how, predicate=args.predicate)
    out = out.drop(columns="index_right", errors="ignore").reset_index(drop=True)
    return dataset_result(f"Spatial join returned {len(out)} row(s).", out,
                          {"predicate": args.predicate, "left_rows": len(left), "right_rows": len(right)})


class IntersectionArgs(ToolArgs):
    left: str = Field(description="Polygon dataset or result_id whose attributes are retained, e.g. districts.")
    right: str = Field(description="Polygon dataset or result_id to intersect with, e.g. incident:<id>.")


@tool(IntersectionArgs, description="""
Intersect each left polygon with the union of the right polygons; keep left attributes and non-zero-area overlaps.
Use communes on the left and an incident on the right for burnt commune areas. Unioning the mask prevents
double-counting overlaps. Returns reusable polygon geometry, ready for measure_area; no map changes.
""")
def intersect_geometries(args: IntersectionArgs, ctx: ToolContext) -> ToolResult:
    left, right = _spatial(args.left, ctx), _spatial(args.right, ctx)
    _polygons(left)
    _polygons(right)
    mask = right.geometry.union_all()
    left.geometry = left.geometry.intersection(mask)
    out = left.loc[left.geometry.area > 0].reset_index(drop=True)
    return dataset_result(f"{len(out)} polygon row(s) overlap the mask.", out,
                          {"method": "intersection with union of right polygons"})


class AreaArgs(ToolArgs):
    source: str = Field(description="Polygon dataset or previous spatial result_id.")
    unit: Literal["ha", "m2", "km2"] = "ha"
    output_column: str | None = Field(None, min_length=1, description="New area column; defaults to area_<unit>.")


@tool(AreaArgs, description="""
Add a polygon area column in ha (default), m2 or km2, measured in the bundle's projected CRS.
For burnt share, measure intersection and full commune areas separately, join by commune code, then calculate percentage.
Keeps geometry for later operations and zoom_map; does not change the map.
""")
def measure_area(args: AreaArgs, ctx: ToolContext) -> ToolResult:
    frame = _spatial(args.source, ctx)
    _polygons(frame)
    column = args.output_column or f"area_{args.unit}"
    check_output(frame, column)
    frame[column] = frame.geometry.area / {"ha": 10_000, "m2": 1, "km2": 1_000_000}[args.unit]
    return dataset_result(f"Measured {len(frame)} polygon row(s) in {args.unit}.", frame,
                          {"area_column": column, "area_unit": args.unit,
                           "area_crs": ctx.bundle.crs_projected})
