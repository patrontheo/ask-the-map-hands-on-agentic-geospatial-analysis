import json

from shapely.geometry import MultiPolygon, Point

from backend.app.agent.baseline import (baseline_footprint, baseline_instructions, footprint_geojson,
                                        simplify_to_budget)


def test_small_geometry_is_left_unchanged():
    square = Point(0, 0).buffer(100, quad_segs=1)
    geom, info = simplify_to_budget(square, 2000)
    assert geom is square and not info.simplified
    assert "Full footprint" in info.label()


def test_dense_geometry_is_simplified_under_budget():
    circle = Point(0, 0).buffer(5000, quad_segs=2000)  # 8,001 vertices
    geom, info = simplify_to_budget(circle, 500)
    assert info.simplified and info.vertices <= 500 < info.vertices_original
    assert info.tolerance_m > 0
    assert info.area_differs_pct < 1
    assert "SIMPLIFIED" in info.label()


def test_fragmented_footprint_meets_budget_without_losing_its_shape():
    big = Point(0, 0).buffer(1000, quad_segs=64)
    fragments = [Point(2000 + 20 * i, 0).buffer(8, quad_segs=2) for i in range(200)]  # a dotted strip
    original = MultiPolygon([big, *fragments])
    geom, info = simplify_to_budget(original, 300)
    assert info.vertices <= 300 < info.vertices_original
    assert info.closing_m > 0 or info.min_part_m2 > 0
    assert info.area_differs_pct < 10
    assert geom.contains(Point(0, 0))


def test_sites_differ_appears_in_label():
    _, info = simplify_to_budget(Point(0, 0).buffer(5000, quad_segs=2000), 500)
    info.sites_differ, info.sites_total = 3, 100
    assert "3 of 100 portfolio sites" in info.label()


def test_fixture_baseline_prompt_labels_footprints(bundle):
    _, info = baseline_footprint(bundle, "flood_test")
    assert not info.simplified
    text = baseline_instructions(bundle)
    assert text.count("Full footprint") == 2


def test_precomputed_baseline_footprint_is_used(tmp_path):
    import shutil

    from backend.app.data import load_bundle
    from tests.conftest import FIXTURE_DIR

    data = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIR, data)
    props = {"simplified": True, "closing_m": 50.0, "min_part_m2": 2000.0, "tolerance_m": 20.0,
             "vertices_original": 9999, "vertices": 5, "parts_original": 7, "parts_kept": 1,
             "area_differs_pct": 4.2, "sites_differ": 2, "sites_total": 13}
    square = [[[3.0, 50.6], [3.1, 50.6], [3.1, 50.7], [3.0, 50.7], [3.0, 50.6]]]
    (data / "events/flood_baseline.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": square}}]}))
    catalog = json.loads((data / "catalog.json").read_text())
    catalog["incidents"][0]["baseline_path"] = "events/flood_baseline.geojson"
    (data / "catalog.json").write_text(json.dumps(catalog))

    bundle = load_bundle(data)
    geom, info = baseline_footprint(bundle, "flood_test")
    assert info.vertices_original == 9999 and type(info.vertices_original) is int
    assert "4.2 % of the area differs" in info.label()
    assert "2 of 13 portfolio sites" in info.label()
    assert geom.bounds == (3.0, 50.6, 3.1, 50.7)


def test_prep_script_writes_files_and_catalog(tmp_path):
    import shutil

    from backend.app.data import load_bundle
    from prep.build_baseline_footprints import build
    from tests.conftest import FIXTURE_DIR

    data = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIR, data)
    report = build(data, max_vertices=3000)
    assert set(report) == {"flood_test", "wildfire_test"}
    assert report["flood_test"]["sites_differ"] == 0 and report["flood_test"]["sites_total"] == 13
    bundle = load_bundle(data)
    assert bundle.incidents["flood_test"].baseline is not None
    assert "Full footprint" in baseline_footprint(bundle, "flood_test")[1].label()


def test_geojson_coordinates_are_rounded(bundle):
    geom, _ = baseline_footprint(bundle, "flood_test")
    g = footprint_geojson(geom)
    lon = g["coordinates"][0][0][0] if g["type"] == "Polygon" else g["coordinates"][0][0][0][0]
    assert len(json.dumps(lon).split(".")[1]) <= 5
