import json

from shapely.geometry import MultiPolygon, Point

from backend.app.footprints import footprint_geojson
from prep.generalise import generalise


def test_small_geometry_is_left_unchanged():
    square = Point(0, 0).buffer(100, quad_segs=1)
    geom, info = generalise(square, 2000)
    assert geom is square and not info.generalised


def test_dense_geometry_is_generalised_under_budget():
    circle = Point(0, 0).buffer(5000, quad_segs=2000)  # 8,001 vertices
    geom, info = generalise(circle, 500)
    assert info.generalised and info.vertices <= 500 < info.vertices_original
    assert info.tolerance_m > 0
    assert info.area_differs_pct < 1


def test_fragmented_footprint_meets_budget_without_losing_its_shape():
    big = Point(0, 0).buffer(1000, quad_segs=64)
    fragments = [Point(2000 + 20 * i, 0).buffer(8, quad_segs=2) for i in range(200)]  # a dotted strip
    original = MultiPolygon([big, *fragments])
    geom, info = generalise(original, 300)
    assert info.vertices <= 300 < info.vertices_original
    assert info.closing_m > 0 or info.min_part_m2 > 0
    assert info.area_differs_pct < 10
    assert geom.contains(Point(0, 0))


def test_geojson_coordinates_are_rounded(bundle):
    geom = bundle.incidents["flood_test"].polygons.geometry.union_all()
    g = footprint_geojson(geom)
    lon = g["coordinates"][0][0][0] if g["type"] == "Polygon" else g["coordinates"][0][0][0][0]
    assert len(json.dumps(lon).split(".")[1]) <= 5
