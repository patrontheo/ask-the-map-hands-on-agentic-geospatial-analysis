"""Spatial tools for the agent. In step-00 they are implemented but not registered, so the chat runs
LLM-only; describing and registering them is the step-01 exercise."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app import analysis
from backend.app.analysis import AnalysisError
from backend.app.data import Bundle
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
    "site_id": "unique site ID", "company_id": "owning company", "address": "street address",
    "district_code": "district", "property_type": "property type", "lon": "longitude (EPSG:4326)",
    "lat": "latitude (EPSG:4326)", "tiv_building_eur": "building TIV (EUR)",
    "tiv_contents_eur": "contents TIV (EUR)", "tiv_eur": "site TIV = building + contents (EUR)",
}


def eur_m(value: float) -> str:
    return f"EUR {value / 1e6:,.1f}M"


class NoArgs(BaseModel):
    pass


@tool(NoArgs, registered=False, description="""
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
        "crs": {"storage": "EPSG:4326", "metric": bundle.crs_projected},
        "definitions": DEFINITIONS,
    }
    ids = ", ".join(i["id"] for i in incidents)
    return ToolResult.ok(
        f"{len(bundle.sites)} sites of {len(bundle.companies)} companies; incidents: {ids}. "
        "Exposed TIV is a screening measure, not a loss.", data=data)


class SelectArgs(BaseModel):
    incident_id: str = Field(description="Incident ID, as listed by describe_data.")


@tool(SelectArgs, registered=False, description="""
Select the portfolio sites inside an incident footprint (boundary included, each site counted once).
Returns the distinct site IDs and their count. Use the returned result_id with summarize_sites.
""")
def select_sites_in_incident(bundle: Bundle, args: SelectArgs, ctx: ToolContext) -> ToolResult:
    sel = analysis.select_sites_in_incident(bundle, args.incident_id)
    fp = analysis.incident_footprint(bundle, args.incident_id)
    return ToolResult.ok(
        f"{sel.n_sites} distinct sites lie in the {args.incident_id} footprint "
        f"(boundary included, {fp.n_polygons} footprint polygon(s) unioned).",
        data={"site_ids": sel.site_ids, "n_sites": sel.n_sites, "metadata": sel.metadata},
        map_actions=[{"type": "highlight_sites", "site_ids": sel.site_ids},
                     {"type": "fit_bounds", "bbox": fp.bbox_4326}],
    )


class SummarizeArgs(BaseModel):
    result_id: str | None = Field(None, description="result_id of a previous select_sites_in_incident call.")
    site_ids: list[str] | None = Field(None, description="Explicit site IDs. Omit both this and result_id "
                                                         "to summarise the whole portfolio.")
    group_by: Literal["none", "company", "district", "property_type"] = "none"
    metric: Literal["n_sites", "tiv"] = Field("tiv", description="Measure used to rank the groups.")

    @model_validator(mode="after")
    def one_source(self):
        if self.result_id is not None and self.site_ids is not None:
            raise ValueError("give either result_id or site_ids, not both")
        return self


@tool(SummarizeArgs, registered=False, description="""
Count distinct sites and sum their TIV (EUR), optionally grouped by company, district or property type,
ranked by the chosen metric. Works on a previous selection (result_id), explicit site IDs, or the whole portfolio.
""")
def summarize_sites(bundle: Bundle, args: SummarizeArgs, ctx: ToolContext) -> ToolResult:
    site_ids = args.site_ids
    scope = "the given sites" if site_ids is not None else "the whole portfolio"
    if args.result_id is not None:
        previous = ctx.store.get(args.result_id)
        if previous is None or "site_ids" not in previous.data:
            raise AnalysisError("unknown_result", f"No site selection with result_id '{args.result_id}'.",
                                "Use the result_id returned by select_sites_in_incident.")
        site_ids = previous.data["site_ids"]
        scope = f"the sites of {args.result_id}"

    s = analysis.summarize_sites(bundle, site_ids, args.group_by, args.metric)
    meta = s.metadata
    text = f"{meta['total_sites']} distinct sites in {scope}, total TIV {eur_m(meta['total_tiv_eur'])}."
    if args.group_by != "none" and len(s.table):
        rank_by = "TIV" if args.metric == "tiv" else "site count"
        top = "; ".join(f"{r.group_name} {eur_m(r.tiv_eur)} ({r.n_sites} site{'s' if r.n_sites != 1 else ''})"
                        for r in s.table.head(3).itertuples())
        text += f" Top by {rank_by}: {top}."
    return ToolResult.ok(text, data={"metadata": meta},
                         table=table_from_df(s.table, units={"tiv_eur": "EUR"}))


class DistanceArgs(BaseModel):
    site_a: str
    site_b: str


@tool(DistanceArgs, registered=False, description="Straight-line distance in metres between two sites, computed in the projected CRS.")
def distance_between_sites(bundle: Bundle, args: DistanceArgs, ctx: ToolContext) -> ToolResult:
    d = analysis.distance_between_sites(bundle, args.site_a, args.site_b)
    return ToolResult.ok(
        f"{args.site_a} and {args.site_b} are {d.distance_m:,.1f} m apart ({d.method}, {d.crs}).",
        data={"distance_m": d.distance_m, "crs": d.crs, "method": d.method},
        map_actions=[{"type": "draw_line", "site_a": args.site_a, "site_b": args.site_b}],
    )
