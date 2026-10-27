import json

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, box

from backend.app.tools.registry import ToolContext, dispatch
from tests.test_table_tools import run, stored


@pytest.fixture
def ctx(bundle):
    return ToolContext(bundle)


def test_spatial_join_boundary_overlap_and_map_chaining(ctx):
    joined = run(ctx, "spatial_join", left="sites", right="incident:flood_test", predicate="covered_by")
    ids = [row["site_id"] for row in joined.table.rows]
    assert "S04" in ids  # exact footprint vertex
    assert ids.count("S02") == 2  # point covered by two polygons
    distinct = run(ctx, "distinct_rows", source=joined.result_id, columns=["site_id"])
    assert sorted(row["site_id"] for row in distinct.table.rows) == ["S01", "S02", "S04", "S05", "S07", "S12"]
    strict = run(ctx, "spatial_join", left="sites", right="incident:flood_test", predicate="within")
    assert "S04" not in [row["site_id"] for row in strict.table.rows]
    highlighted = dispatch("highlight_sites", {"result_id": distinct.result_id}, ctx)
    assert highlighted.data["n_sites"] == 6
    zoomed = dispatch("zoom_map", {"result_id": distinct.result_id}, ctx)
    assert zoomed.status == "ok" and zoomed.map_actions[0]["type"] == "fit_bounds"
    assert abs(zoomed.map_actions[0]["bbox"][0]) < 180


def test_spatial_join_left_rows_and_duplicate_names(ctx):
    joined = run(ctx, "spatial_join", left="sites", right="districts", how="left")
    assert joined.table.total_rows == 13
    assert {"district_code", "district_code_right"} <= set(ctx.get_frame(joined.result_id).columns)
    unmatched = run(ctx, "spatial_join", left="sites", right="incident:flood_test", how="left")
    assert any(row["incident_id"] is None for row in unmatched.table.rows)


def test_intersection_union_prevents_double_counted_area(ctx):
    clipped = run(ctx, "intersect_geometries", left="districts", right="incident:flood_test")
    burnt = run(ctx, "measure_area", source=clipped.result_id, output_column="burnt_area_ha")
    # Two 4 km² squares, overlapping by 0.75 km², all in D1.
    assert burnt.table.total_rows == 1
    assert burnt.table.rows[0]["district_code"] == "D1"
    assert burnt.table.rows[0]["burnt_area_ha"] == pytest.approx(725, abs=1e-6)
    assert burnt.data["schema"]["burnt_area_ha"]["unit"] == "ha"
    json.dumps(burnt.model_dump(), allow_nan=False)
    assert ctx.get_frame("districts").crs.to_epsg() == 4326


@pytest.mark.parametrize("unit,expected", [("ha", 3600), ("m2", 36_000_000), ("km2", 36)])
def test_area_units_and_projection(ctx, unit, expected):
    result = run(ctx, "measure_area", source="districts", unit=unit)
    assert result.table.rows[0][f"area_{unit}"] == pytest.approx(expected, rel=1e-8)
    assert result.data["area_crs"] == "EPSG:2154"


def test_intersection_handles_empty_masks_holes_and_invalid_polygons(ctx):
    ring = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], holes=[[(2, 2), (8, 2), (8, 8), (2, 8)]])
    left = stored(ctx, gpd.GeoDataFrame({"id": ["one"]}, geometry=[box(0, 0, 10, 10)], crs=2154))
    right = stored(ctx, gpd.GeoDataFrame(geometry=[ring], crs=2154))
    result = run(ctx, "intersect_geometries", left=left, right=right)
    assert ctx.get_frame(result.result_id).geometry.area.iloc[0] == pytest.approx(64)
    bowtie = stored(ctx, gpd.GeoDataFrame(geometry=[Polygon([(0, 0), (10, 10), (0, 10), (10, 0)])], crs=2154))
    repaired = run(ctx, "intersect_geometries", left=left, right=bowtie)
    assert ctx.get_frame(repaired.result_id).geometry.is_valid.all()
    empty = stored(ctx, gpd.GeoDataFrame(geometry=[], crs=2154))
    assert run(ctx, "intersect_geometries", left=left, right=empty).table.total_rows == 0


def test_spatial_operations_reject_nonspatial_inputs(ctx):
    for name, args in (
        ("spatial_join", {"left": "sites", "right": "companies"}),
        ("intersect_geometries", {"left": "companies", "right": "districts"}),
        ("measure_area", {"source": "companies"}),
    ):
        result = dispatch(name, args, ctx)
        assert result.error.code == "invalid_dataset" and result.error.hint
    assert dispatch("measure_area", {"source": "sites"}, ctx).error.code == "invalid_geometry"
    missing_crs = stored(ctx, gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)]))
    assert dispatch("measure_area", {"source": missing_crs}, ctx).error.code == "invalid_dataset"
