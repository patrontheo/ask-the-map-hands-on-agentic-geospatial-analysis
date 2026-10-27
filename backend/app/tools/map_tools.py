"""Map tools: visibility, highlight and camera. Display only; they never select or compute."""

from pydantic import Field, model_validator

from backend.app import analysis
from backend.app.analysis import AnalysisError
from backend.app.data import Bundle
from backend.app.layers import layer_bbox, layer_ids
from backend.app.tools.registry import ToolArgs, ToolContext, tool
from backend.app.tools.result import ToolResult, is_spatial


class LayerArgs(ToolArgs):
    layer_id: str = Field(description="Map layer ID from describe_data, e.g. 'sites' or 'incident:<id>'.")


class SiteIdsArgs(ToolArgs):
    site_ids: list[str] | None = Field(None, description="Site IDs to highlight; an empty list clears the highlight.")
    result_id: str | None = Field(None, description="Dataset result with a site_id column; use instead of site_ids.")

    @model_validator(mode="after")
    def one_source(self):
        if (self.site_ids is None) == (self.result_id is None):
            raise ValueError("give either site_ids or result_id")
        return self


class ZoomArgs(ToolArgs):
    layer_id: str | None = Field(None, description="Layer to zoom to: 'sites', 'districts' or 'incident:<id>'.")
    site_ids: list[str] | None = Field(None, description="Sites to zoom to.")
    result_id: str | None = Field(None, description="A spatial dataset result to zoom to.")

    @model_validator(mode="after")
    def at_least_one(self):
        if self.layer_id is None and not self.site_ids and self.result_id is None:
            raise ValueError("give layer_id, site_ids, result_id, or a combination")
        return self


def _check_layer(bundle: Bundle, layer_id: str) -> None:
    if layer_id not in layer_ids(bundle):
        raise AnalysisError("unknown_layer", f"Unknown layer_id '{layer_id}'.",
                            f"Valid layer_id values: {', '.join(layer_ids(bundle))}.")


@tool(LayerArgs, description="Show a map layer. Keeps the current camera position; use zoom_map to move it.")
def show_layer(args: LayerArgs, ctx: ToolContext) -> ToolResult:
    _check_layer(ctx.bundle, args.layer_id)
    return ToolResult.ok(f"Showing {args.layer_id}.",
                         map_actions=[{"type": "show_layer", "layer_id": args.layer_id}])


@tool(LayerArgs, description="Hide a layer from the map.")
def hide_layer(args: LayerArgs, ctx: ToolContext) -> ToolResult:
    _check_layer(ctx.bundle, args.layer_id)
    return ToolResult.ok(f"Hid {args.layer_id}.", map_actions=[{"type": "hide_layer", "layer_id": args.layer_id}])


@tool(SiteIdsArgs, description="""
Highlight explicit site IDs or the sites in a dataset result. Empty input clears the highlight.
Makes sites visible and keeps the current camera position. Display only; it does not perform a selection.
""")
def highlight_sites(args: SiteIdsArgs, ctx: ToolContext) -> ToolResult:
    site_ids = args.site_ids
    if args.result_id is not None:
        frame = ctx.get_frame(args.result_id)
        if "site_id" not in frame or frame.site_id.isna().any():
            raise AnalysisError("invalid_dataset", "Highlighting requires a complete site_id column.",
                                "Use a result containing site rows, or pass explicit site_ids.")
        site_ids = frame.site_id.tolist()
    site_ids = list(dict.fromkeys(site_ids))
    if not site_ids:
        return ToolResult.ok("Cleared the highlighted sites.", data={"n_sites": 0},
                             map_actions=[{"type": "clear_highlight"}])
    analysis.check_site_ids(ctx.bundle, site_ids)
    return ToolResult.ok(
        f"Highlighted {len(site_ids)} site(s) on the map.",
        data={"site_ids": site_ids, "n_sites": len(site_ids)},
        map_actions=[{"type": "highlight_sites", "site_ids": site_ids}],
    )


@tool(ZoomArgs, description="Zoom to a layer, site IDs, a spatial dataset result, or their combined bounds.")
def zoom_map(args: ZoomArgs, ctx: ToolContext) -> ToolResult:
    boxes, targets = [], []
    if args.layer_id is not None:
        _check_layer(ctx.bundle, args.layer_id)
        boxes.append(layer_bbox(ctx.bundle, args.layer_id))
        targets.append(args.layer_id)
    if args.site_ids:
        analysis.check_site_ids(ctx.bundle, args.site_ids)
        boxes.append([float(v) for v in ctx.bundle.sites.loc[args.site_ids].total_bounds])
        targets.append(f"{len(args.site_ids)} site(s)")
    if args.result_id is not None:
        frame = ctx.get_frame(args.result_id)
        if not is_spatial(frame) or frame.crs is None:
            raise AnalysisError("invalid_dataset", "Zooming to a result requires geometry and a CRS.",
                                "Use a spatial dataset result, a layer_id or explicit site_ids.")
        valid = frame.geometry.notna() & ~frame.geometry.is_empty
        if not valid.any():
            raise AnalysisError("invalid_dataset", "This result has no non-empty geometry to zoom to.",
                                "Choose a non-empty spatial result.")
        boxes.append([float(v) for v in frame.loc[valid].to_crs("EPSG:4326").total_bounds])
        targets.append(args.result_id)
    bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    return ToolResult.ok(f"Zoomed to {' and '.join(targets)}.", map_actions=[{"type": "fit_bounds", "bbox": bbox}])
