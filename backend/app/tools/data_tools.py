"""Step-00 tools: load the data and show it on the map. None of them computes anything spatial."""

from pydantic import BaseModel, Field, model_validator

from backend.app import analysis
from backend.app.analysis import AnalysisError
from backend.app.data import Bundle
from backend.app.footprints import FootprintNotPrepared, footprint_geojson, simplified_footprint
from backend.app.layers import layer_bbox, layer_ids
from backend.app.tools.registry import ToolContext, tool
from backend.app.tools.result import ToolResult, table_from_df

DEFINITIONS = {
    "inclusion": "A site is in an incident footprint if the footprint covers its address point, "
                 "boundary included. Footprint polygons of one incident are unioned, so each site counts once.",
    "tiv_eur": "Total insured value of a site = building + contents, in EUR. Business interruption is excluded.",
    "exposed_tiv": "Sum of tiv_eur over the distinct sites in the footprint. This is a screening measure: "
                   "it is not damage, loss, or an insurance payout.",
    "data": "Footprints are real (Copernicus EMS). Sites, companies and insured values are synthetic.",
}

SITE_COLUMNS = {
    "site_id": "unique site ID", "company_id": "owning company", "company_name": "company name",
    "address": "street address", "city": "city", "district_name": "district", "property_type": "property type",
    "lon": "longitude (EPSG:4326)", "lat": "latitude (EPSG:4326)", "tiv_building_eur": "building TIV (EUR)",
    "tiv_contents_eur": "contents TIV (EUR)", "tiv_eur": "site TIV = building + contents (EUR)",
}
EUR_UNITS = {"tiv_building_eur": "EUR", "tiv_contents_eur": "EUR", "tiv_eur": "EUR"}


class NoArgs(BaseModel):
    pass


class IncidentArgs(BaseModel):
    incident_id: str = Field(description="Incident ID, as listed by describe_data.")


class SiteIdsArgs(BaseModel):
    site_ids: list[str] = Field(description="Site IDs to highlight. An empty list clears the highlight.")


class ZoomArgs(BaseModel):
    layer_id: str | None = Field(None, description="Layer to zoom to: 'sites', 'districts' or 'incident:<id>'.")
    site_ids: list[str] | None = Field(None, description="Sites to zoom to.")

    @model_validator(mode="after")
    def at_least_one(self):
        if self.layer_id is None and not self.site_ids:
            raise ValueError("give layer_id, site_ids, or both")
        return self


class LayerArgs(BaseModel):
    layer_id: str = Field(description="Layer to hide, e.g. 'sites', 'districts' or 'incident:<id>'.")


def _check_layer(bundle: Bundle, layer_id: str) -> None:
    if layer_id not in layer_ids(bundle):
        raise AnalysisError("unknown_layer", f"Unknown layer_id '{layer_id}'.",
                            f"Valid layer_id values: {', '.join(layer_ids(bundle))}.")


def _sites_bbox(bundle: Bundle, site_ids: list[str]) -> list[float]:
    return [float(v) for v in bundle.sites.loc[site_ids].total_bounds]


@tool(NoArgs, description="""
Describe the available data: incidents (IDs, peril, date, source), portfolio columns and units,
coordinate systems, and the screening definitions. Call this first when you do not know an incident ID.
""")
def describe_data(bundle: Bundle, args: NoArgs, ctx: ToolContext) -> ToolResult:
    incidents = [{k: m.get(k) for k in ("id", "peril", "name", "date", "source")} for m in bundle.catalog["incidents"]]
    data = {
        "incidents": incidents,
        "portfolio": {"n_sites": len(bundle.sites), "n_companies": len(bundle.companies),
                      "columns": SITE_COLUMNS, "currency": "EUR",
                      "property_types": sorted(bundle.sites.property_type.unique())},
        "districts": {"n_districts": len(bundle.districts)},
        "layers": layer_ids(bundle),
        "crs": {"storage": "EPSG:4326", "metric": bundle.crs_projected},
        "definitions": DEFINITIONS,
    }
    ids = ", ".join(i["id"] for i in incidents)
    return ToolResult.ok(
        f"{len(bundle.sites)} sites of {len(bundle.companies)} companies; incidents: {ids}. "
        "Exposed TIV is a screening measure, not a loss.", data=data)


@tool(NoArgs, description="""
Load the portfolio: one row per site with company, address, district, property type, coordinates and TIV (EUR).
Also shows the sites on the map.
""")
def load_portfolio(bundle: Bundle, args: NoArgs, ctx: ToolContext) -> ToolResult:
    sites = bundle.sites.join(bundle.companies.company_name, on="company_id")
    table = sites[list(SITE_COLUMNS)].round({"lon": 5, "lat": 5}).reset_index(drop=True)
    return ToolResult.ok(
        f"Loaded {len(table)} sites of {len(bundle.companies)} companies; they are shown on the map.",
        data={"n_sites": len(table), "n_companies": len(bundle.companies)},
        table=table_from_df(table, id_field="site_id", units=EUR_UNITS),
        map_actions=[{"type": "show_layer", "layer_id": "sites"},
                     {"type": "fit_bounds", "bbox": layer_bbox(bundle, "sites")}],
    )


@tool(IncidentArgs, description="""
Load an incident footprint and show it on the map. Returns its metadata and a simplified copy of the
footprint geometry (EPSG:4326) that you can read; the label states how much it differs from the full footprint.
""")
def load_incident(bundle: Bundle, args: IncidentArgs, ctx: ToolContext) -> ToolResult:
    fp = analysis.incident_footprint(bundle, args.incident_id)
    try:
        geom, info = simplified_footprint(bundle, args.incident_id)
        reading = {"label": info.label(), "crs": "EPSG:4326", "geometry": footprint_geojson(geom)}
    except FootprintNotPrepared:
        reading = {"label": "Not available: the simplified copy of this footprint has not been prepared, "
                            "so its geometry cannot be read."}
    meta = fp.meta
    area_km2 = round(fp.union_projected.area / 1e6, 2)
    return ToolResult.ok(
        f"Showing the {meta.get('peril')} footprint {args.incident_id} ({meta.get('name')}, {meta.get('date')}) "
        f"on the map: {fp.n_polygons} polygon(s), {area_km2:,} km².",
        data={"incident_id": args.incident_id, "peril": meta.get("peril"), "name": meta.get("name"),
              "date": meta.get("date"), "source": meta.get("source"), "n_polygons": fp.n_polygons,
              "area_km2": area_km2, "bbox": fp.bbox_4326,
              "footprint_for_reading": reading},
        map_actions=[{"type": "show_layer", "layer_id": f"incident:{args.incident_id}"},
                     {"type": "fit_bounds", "bbox": fp.bbox_4326}],
    )


@tool(NoArgs, description="Load the district boundaries (code and name) and show them on the map.")
def load_districts(bundle: Bundle, args: NoArgs, ctx: ToolContext) -> ToolResult:
    table = bundle.districts[["district_code", "district_name"]].reset_index(drop=True)
    return ToolResult.ok(
        f"Loaded {len(table)} districts; they are shown on the map.",
        data={"n_districts": len(table)},
        table=table_from_df(table, id_field="district_code"),
        map_actions=[{"type": "show_layer", "layer_id": "districts"},
                     {"type": "fit_bounds", "bbox": layer_bbox(bundle, "districts")}],
    )


@tool(SiteIdsArgs, description="""
Highlight the given sites on the map. Display only: it does not check whether the sites are inside a footprint.
""")
def highlight_sites(bundle: Bundle, args: SiteIdsArgs, ctx: ToolContext) -> ToolResult:
    site_ids = list(dict.fromkeys(args.site_ids))
    if not site_ids:
        return ToolResult.ok("Cleared the highlighted sites.", data={"n_sites": 0},
                             map_actions=[{"type": "clear_highlight"}])
    analysis.check_site_ids(bundle, site_ids)
    return ToolResult.ok(
        f"Highlighted {len(site_ids)} site(s) on the map.",
        data={"site_ids": site_ids, "n_sites": len(site_ids)},
        map_actions=[{"type": "show_layer", "layer_id": "sites"},
                     {"type": "highlight_sites", "site_ids": site_ids},
                     {"type": "fit_bounds", "bbox": _sites_bbox(bundle, site_ids)}],
    )


@tool(ZoomArgs, description="Zoom the map to a layer, to a set of sites, or to both together.")
def zoom_map(bundle: Bundle, args: ZoomArgs, ctx: ToolContext) -> ToolResult:
    boxes, targets = [], []
    if args.layer_id is not None:
        _check_layer(bundle, args.layer_id)
        boxes.append(layer_bbox(bundle, args.layer_id))
        targets.append(args.layer_id)
    if args.site_ids:
        analysis.check_site_ids(bundle, args.site_ids)
        boxes.append(_sites_bbox(bundle, args.site_ids))
        targets.append(f"{len(args.site_ids)} site(s)")
    bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    return ToolResult.ok(f"Zoomed to {' and '.join(targets)}.", map_actions=[{"type": "fit_bounds", "bbox": bbox}])


@tool(LayerArgs, description="Hide a layer from the map.")
def hide_layer(bundle: Bundle, args: LayerArgs, ctx: ToolContext) -> ToolResult:
    _check_layer(bundle, args.layer_id)
    return ToolResult.ok(f"Hid {args.layer_id}.", map_actions=[{"type": "hide_layer", "layer_id": args.layer_id}])
