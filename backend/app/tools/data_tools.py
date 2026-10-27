"""Data tools: discover and read datasets. They never change the map."""

from pydantic import Field

from backend.app.analysis import AnalysisError
from backend.app.datasets import dataset_frame, dataset_ids
from backend.app.footprints import footprint_geojson
from backend.app.layers import layer_ids
from backend.app.tools.registry import ToolArgs, ToolContext, tool
from backend.app.tools.result import ToolResult, dataset_result, frame_info, id_field, is_spatial

DEFINITIONS = {
    "inclusion": "A site is affected if any of its buildings intersects the incident footprint, including "
                 "boundary contact, even if its map pinpoint is outside. Count each site_id once. "
                 "Use address-point coverage only as an explicit fallback when no building dataset is available.",
    "tiv_eur": "Total insured value of a site = building + contents, in EUR. Business interruption is excluded.",
    "exposed_tiv": "Sum of the full tiv_eur of each distinct affected site, not prorated by intersected area. This is a screening measure: "
                   "it is not damage, loss, or an insurance payout.",
    "data": "Footprints are real (Copernicus EMS). Sites, companies and insured values are synthetic.",
}

SITE_COLUMNS = {
    "site_id": "unique site ID", "company_id": "owning company", "company_name": "company name",
    "address": "street address", "city": "city", "district_name": "district", "property_type": "property type",
    "lon": "longitude (EPSG:4326)", "lat": "latitude (EPSG:4326)", "tiv_building_eur": "building TIV (EUR)",
    "tiv_contents_eur": "contents TIV (EUR)", "tiv_eur": "site TIV = building + contents (EUR)",
}


class NoArgs(ToolArgs):
    pass


class DatasetArgs(ToolArgs):
    dataset_id: str = Field(description="Dataset ID from describe_data, or a previous dataset result_id.")
    include_geometry: bool = Field(False, description="Include rounded GeoJSON for reading spatial data. "
                                                   "Full geometry is always retained in the backend.")


@tool(NoArgs, description="""
Describe the available datasets and map layers: IDs, schemas, units, CRS, incident metadata and definitions.
Call this first when IDs are unknown. Use get_dataset to read data; show_layer and zoom_map control display.
""")
def describe_data(args: NoArgs, ctx: ToolContext) -> ToolResult:
    bundle = ctx.bundle
    incidents = [{k: m.get(k) for k in ("id", "peril", "name", "date", "source")} for m in bundle.catalog["incidents"]]
    data = {
        "incidents": incidents,
        "portfolio": {"n_sites": len(bundle.sites), "n_companies": len(bundle.companies),
                      "columns": SITE_COLUMNS, "currency": "EUR",
                      "property_types": sorted(bundle.sites.property_type.unique())},
        "districts": {"n_districts": len(bundle.districts)},
        "layers": layer_ids(bundle),
        "datasets": {name: frame_info(dataset_frame(bundle, name)) for name in dataset_ids(bundle)},
        "crs": {"storage": "EPSG:4326", "metric": bundle.crs_projected},
        "definitions": DEFINITIONS,
    }
    ids = ", ".join(i["id"] for i in incidents)
    return ToolResult.ok(
        f"{len(bundle.sites)} sites of {len(bundle.companies)} companies; incidents: {ids}. "
        "Exposed TIV is a screening measure, not a loss.", data=data)


@tool(DatasetArgs, description="""
Read a named dataset or previous dataset result: attributes, schema, row count and CRS.
Returns a result_id for later tools; full data/geometry stays in the backend. Request include_geometry
for rounded GeoJSON when reasoning over geometry yourself. This tool does not change the map.
""")
def get_dataset(args: DatasetArgs, ctx: ToolContext) -> ToolResult:
    frame = ctx.get_frame(args.dataset_id)
    data = {"dataset_id": args.dataset_id}
    if args.dataset_id.startswith("incident:"):
        data["metadata"] = ctx.bundle.incidents[args.dataset_id.removeprefix("incident:")].meta
    if args.include_geometry:
        if not is_spatial(frame):
            raise AnalysisError("invalid_dataset", f"Dataset '{args.dataset_id}' has no geometry.",
                                "Omit include_geometry when reading a non-spatial table.")
        data["geometry"] = _feature_collection(frame)
    return dataset_result(f"Read {len(frame)} row(s) from {args.dataset_id}.", frame, data)


def _feature_collection(frame) -> dict:
    """Rounded GeoJSON in EPSG:4326, whatever CRS an intermediate result uses."""
    key = id_field(frame)
    geoms = frame.geometry.to_crs("EPSG:4326") if frame.crs else frame.geometry
    ids = frame[key].tolist() if key else [None] * len(frame)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {key: i} if key else {},
         "geometry": footprint_geojson(g) if g is not None and not g.is_empty else None}
        for i, g in zip(ids, geoms)
    ]}
