"""Independent re-check of site selection: raw JSON/CSV, pyproj, pure-Python ray casting (no geopandas/shapely)."""

import csv
import json
from pathlib import Path

import pytest
from pyproj import Transformer

from backend.app.analysis import select_sites_in_incident
from backend.app.data import REPO_ROOT, load_bundle
from tests.conftest import FIXTURE_DIR

EPS = 1e-6  # metres; tolerance for "on the boundary"
BUNDLES = [FIXTURE_DIR] + ([REPO_ROOT / "data"] if (REPO_ROOT / "data" / "catalog.json").exists() else [])


def on_segment(px, py, ax, ay, bx, by):
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
    if length == 0:
        return abs(px - ax) <= EPS and abs(py - ay) <= EPS
    if abs(cross) / length > EPS:
        return False
    return min(ax, bx) - EPS <= px <= max(ax, bx) + EPS and min(ay, by) - EPS <= py <= max(ay, by) + EPS


def ring_position(px, py, ring):
    """'boundary', 'inside' or 'outside' for a closed ring."""
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        if on_segment(px, py, ax, ay, bx, by):
            return "boundary"
        if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return "inside" if inside else "outside"


def polygon_covers(px, py, rings):
    exterior = ring_position(px, py, rings[0])
    if exterior == "outside":
        return False
    return all(ring_position(px, py, hole) != "inside" for hole in rings[1:])


def polygons_of(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    return []


def independent_selection(data_dir: Path) -> dict[str, list[str]]:
    catalog = json.loads((data_dir / "catalog.json").read_text())
    to_proj = Transformer.from_crs("EPSG:4326", catalog["crs_projected"], always_xy=True)
    with open(data_dir / catalog["portfolio"]["sites"]) as f:
        sites = [(r["site_id"], *to_proj.transform(float(r["lon"]), float(r["lat"]))) for r in csv.DictReader(f)]

    out = {}
    for meta in catalog["incidents"]:
        features = json.loads((data_dir / meta["path"]).read_text())["features"]
        polys = [[[to_proj.transform(*pt[:2]) for pt in ring] for ring in poly]
                 for feat in features for poly in polygons_of(feat["geometry"])]
        out[meta["id"]] = sorted(sid for sid, x, y in sites if any(polygon_covers(x, y, p) for p in polys))
    return out


@pytest.mark.parametrize("data_dir", BUNDLES, ids=lambda p: p.parent.name + "/" + p.name)
def test_selection_matches_independent_implementation(data_dir):
    bundle = load_bundle(data_dir)
    for incident_id, expected in independent_selection(data_dir).items():
        assert select_sites_in_incident(bundle, incident_id).site_ids == expected, incident_id


def test_expected_json_matches_independent_selection():
    expected_path = REPO_ROOT / "tests" / "expected.json"
    if not expected_path.exists():
        pytest.skip("tests/expected.json not generated yet (data not frozen)")
    expected = json.loads(expected_path.read_text())
    independent = independent_selection(REPO_ROOT / "data")
    for incident_id, ref in expected["incidents"].items():
        assert ref["site_ids"] == independent[incident_id], incident_id
