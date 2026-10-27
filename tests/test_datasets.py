import json
from dataclasses import replace

import geopandas as gpd
import pandas as pd
import pytest

from backend.app.data import REPO_ROOT, load_bundle
from backend.app.datasets import dataset_ids
from backend.app.tools.registry import ToolContext, dispatch
from backend.app.tools.result import ToolResult, dataset_result, to_llm_payload


@pytest.fixture
def ctx(bundle):
    return ToolContext(bundle)


def test_discovery_lists_dataset_schemas_units_and_spatial_metadata(ctx):
    result = dispatch("describe_data", {}, ctx)
    datasets = result.data["datasets"]
    assert {"sites", "companies", "districts", "incident:flood_test", "incident:wildfire_test"} <= set(datasets)
    assert datasets["sites"]["schema"]["tiv_eur"]["unit"] == "EUR"
    assert datasets["sites"]["schema"]["geometry"]["type"] == "geometry"
    assert datasets["sites"]["crs"] == "EPSG:4326"
    assert datasets["companies"]["crs"] is None
    assert result.map_actions == []


@pytest.mark.parametrize("dataset_id,n_rows,spatial", [
    ("sites", 13, True), ("companies", 4, False), ("districts", 2, True),
    ("incident:flood_test", 2, True), ("incident:wildfire_test", 1, True),
])
def test_named_datasets_return_reusable_data_without_display(ctx, dataset_id, n_rows, spatial):
    result = dispatch("get_dataset", {"dataset_id": dataset_id}, ctx)
    assert result.status == "ok", result.error
    assert result.data["n_rows"] == result.table.total_rows == n_rows
    assert result.map_actions == []
    assert "geometry" not in result.data
    assert "geometry" not in [column.name for column in result.table.columns]
    frame = ctx.get_frame(result.result_id)
    assert isinstance(frame, gpd.GeoDataFrame) == spatial
    assert len(frame) == n_rows
    payload = result.model_dump()
    assert "_frame" not in payload
    json.dumps(payload)  # A private GeoDataFrame must never break API serialization.
    json.dumps(to_llm_payload(result))


def test_result_reference_preserves_geometry_and_precision(ctx, bundle):
    result = dispatch("get_dataset", {"dataset_id": "sites"}, ctx)
    frame = ctx.get_frame(result.result_id)
    assert frame.crs == bundle.sites.crs
    assert frame.geometry.equals(bundle.sites.geometry)
    assert frame.lon.equals(bundle.sites.lon)
    assert frame.lat.equals(bundle.sites.lat)
    assert "company_name" in frame and "district_code" in frame
    reread = dispatch("get_dataset", {"dataset_id": result.result_id}, ctx)
    assert reread.status == "ok"
    pd.testing.assert_frame_equal(ctx.get_frame(reread.result_id), frame)


def test_reading_sources_and_results_returns_independent_copies(ctx, bundle):
    original_lon = bundle.sites.lon.iloc[0]
    source = ctx.get_frame("sites")
    source.iloc[0, source.columns.get_loc("lon")] = 0
    assert bundle.sites.lon.iloc[0] == original_lon
    result = dispatch("get_dataset", {"dataset_id": "sites"}, ctx)
    frame = ctx.get_frame(result.result_id)
    frame.iloc[0, frame.columns.get_loc("lon")] = 0
    assert ctx.get_frame(result.result_id).lon.iloc[0] == original_lon


def test_tabular_intermediates_use_the_same_result_contract(ctx):
    result = ToolResult.ok("Example intermediate", frame=pd.DataFrame({"company_id": ["C01"], "amount": [12]}))
    result.result_id = ctx.store.next_id()
    ctx.store.add(result)
    reread = dispatch("get_dataset", {"dataset_id": result.result_id}, ctx)
    assert reread.status == "ok"
    assert reread.table.rows == [{"company_id": "C01", "amount": 12}]


def test_result_references_are_scoped_to_the_session(ctx, bundle):
    result = dispatch("get_dataset", {"dataset_id": "sites"}, ctx)
    other = ToolContext(bundle)
    missing = dispatch("get_dataset", {"dataset_id": result.result_id}, other)
    assert missing.error.code == "unknown_result"
    shown = dispatch("show_layer", {"layer_id": "sites"}, ctx)
    invalid = dispatch("get_dataset", {"dataset_id": shown.result_id}, ctx)
    assert invalid.error.code == "invalid_dataset"


def test_optional_geometry_is_readable_without_merging_polygons(ctx, bundle):
    result = dispatch("get_dataset", {"dataset_id": "incident:flood_test", "include_geometry": True}, ctx)
    assert result.status == "ok"
    features = result.data["geometry"]["features"]
    assert len(features) == len(bundle.incidents["flood_test"].polygons) == 2
    assert all(feature["geometry"]["type"] == "Polygon" for feature in features)
    assert ctx.get_frame(result.result_id).geometry.equals(bundle.incidents["flood_test"].polygons.geometry)
    assert result.data["metadata"]["source"] == "fixture"
    assert not result.map_actions


def test_nonspatial_geometry_request_returns_a_hint(ctx):
    result = dispatch("get_dataset", {"dataset_id": "companies", "include_geometry": True}, ctx)
    assert result.error.code == "invalid_dataset"
    assert "include_geometry" in result.error.hint


def test_optional_dataset_discovery_matches_the_bundle(bundle):
    assert {"buildings", "parcels"}.isdisjoint(dataset_ids(bundle))
    extended = replace(bundle, buildings=bundle.districts, parcels=bundle.districts)
    assert {"buildings", "parcels"} <= set(dataset_ids(extended))
    for name in ("buildings", "parcels"):
        result = dispatch("get_dataset", {"dataset_id": name}, ToolContext(extended))
        assert result.status == "ok" and result.data["n_rows"] == 2


def test_highlight_and_zoom_can_consume_dataset_results(ctx):
    result = dispatch("get_dataset", {"dataset_id": "sites"}, ctx)
    highlighted = dispatch("highlight_sites", {"result_id": result.result_id}, ctx)
    assert highlighted.status == "ok" and highlighted.data["n_sites"] == 13
    assert highlighted.map_actions == [{"type": "highlight_sites", "site_ids": list(ctx.bundle.sites.index)}]
    zoomed = dispatch("zoom_map", {"result_id": result.result_id}, ctx)
    assert zoomed.status == "ok" and zoomed.map_actions[0]["type"] == "fit_bounds"
    assert zoomed.map_actions[0]["bbox"] == list(ctx.bundle.sites.total_bounds)


def test_highlighted_sites_can_be_zoomed_to_by_result_id(ctx):
    highlighted = dispatch("highlight_sites", {"site_ids": ["S01", "S03"]}, ctx)
    zoomed = dispatch("zoom_map", {"result_id": highlighted.result_id}, ctx)
    assert zoomed.status == "ok"
    assert zoomed.map_actions[0]["bbox"] == list(ctx.bundle.sites.loc[["S01", "S03"]].total_bounds)
    assert highlighted.table is None  # display tool: nothing extra under the answer


def test_zoom_converts_projected_results_to_map_coordinates(ctx):
    result = ToolResult.ok("Projected intermediate", frame=ctx.bundle.sites.to_crs(ctx.bundle.crs_projected))
    result.result_id = ctx.store.next_id()
    ctx.store.add(result)
    zoomed = dispatch("zoom_map", {"result_id": result.result_id}, ctx)
    assert zoomed.status == "ok"
    assert zoomed.map_actions[0]["bbox"] == pytest.approx(list(ctx.bundle.sites.total_bounds), abs=1e-8)


def test_projected_results_are_read_back_as_map_coordinates(ctx):
    result = ToolResult.ok("Projected intermediate", frame=ctx.bundle.sites.to_crs(ctx.bundle.crs_projected))
    result.result_id = ctx.store.next_id()
    ctx.store.add(result)
    read = dispatch("get_dataset", {"dataset_id": result.result_id, "include_geometry": True}, ctx)
    lon, lat = read.data["geometry"]["features"][0]["geometry"]["coordinates"]
    assert (lon, lat) == pytest.approx((ctx.bundle.sites.lon.iloc[0], ctx.bundle.sites.lat.iloc[0]), abs=1e-5)


def test_dataset_result_gives_new_tools_the_get_dataset_contract(ctx):
    frame = pd.DataFrame({"company_id": ["C01", "C02"], "exposed_tiv_eur": [1.5, 0.0]})
    result = dataset_result("Example", frame, {"measure": "exposed TIV"})
    assert result.table.id_field == "company_id"
    assert result.data["n_rows"] == 2 and result.data["measure"] == "exposed TIV"
    assert result.data["schema"]["exposed_tiv_eur"]["unit"] == "EUR"
    assert result._frame is frame


def test_unsuitable_result_inputs_fail_and_empty_highlight_clears(ctx):
    companies = dispatch("get_dataset", {"dataset_id": "companies"}, ctx)
    assert dispatch("highlight_sites", {"result_id": companies.result_id}, ctx).error.code == "invalid_dataset"
    assert dispatch("zoom_map", {"result_id": companies.result_id}, ctx).error.code == "invalid_dataset"
    empty = ToolResult.ok("Empty spatial intermediate", frame=ctx.bundle.sites.iloc[:0].copy())
    empty.result_id = ctx.store.next_id()
    ctx.store.add(empty)
    assert dispatch("highlight_sites", {"result_id": empty.result_id}, ctx).map_actions == [{"type": "clear_highlight"}]
    assert dispatch("zoom_map", {"result_id": empty.result_id}, ctx).error.code == "invalid_dataset"
    both = dispatch("highlight_sites", {"site_ids": ["S01"], "result_id": empty.result_id}, ctx)
    assert both.error.code == "invalid_arguments"


def test_incident_processing_metadata_is_preserved():
    bundle = load_bundle(REPO_ROOT / "data")
    incident_id = next(iter(bundle.incidents))
    result = dispatch("get_dataset", {"dataset_id": f"incident:{incident_id}"}, ToolContext(bundle))
    assert result.status == "ok"
    assert result.data["metadata"]["processing"] == bundle.incidents[incident_id].meta["processing"]
