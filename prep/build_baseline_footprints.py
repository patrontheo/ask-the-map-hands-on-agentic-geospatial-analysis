"""Precompute the simplified footprints given to the LLM-only baseline (organiser step, after the data bundle exists).

For each incident in <data_dir>/catalog.json: generalise the full footprint to the vertex budget, count the
portfolio sites it classifies differently from the full footprint, write events/<id>_baseline.geojson and
record it as `baseline_path` in the catalog.

Run: uv run python prep/build_baseline_footprints.py [data_dir] [--max-vertices N]
"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run by path: make the repo root importable

import geopandas as gpd

from backend.app.agent.baseline import MAX_VERTICES, footprint_geojson, simplify_to_budget
from backend.app.analysis import incident_footprint
from backend.app.data import REPO_ROOT, load_bundle


def build(data_dir: Path, max_vertices: int) -> dict[str, dict]:
    bundle = load_bundle(data_dir)
    catalog_path = data_dir / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    report = {}
    for meta in catalog["incidents"]:
        start = time.perf_counter()
        full = incident_footprint(bundle, meta["id"]).union_projected
        simplified, info = simplify_to_budget(full, max_vertices)
        in_full = bundle.sites_projected.map(full.covers)
        in_simplified = bundle.sites_projected.map(simplified.covers)
        info.sites_differ = int((in_full != in_simplified).sum())
        info.sites_total = len(bundle.sites)

        geom_4326 = gpd.GeoSeries([simplified], crs=bundle.crs_projected).to_crs("EPSG:4326").iloc[0]
        rel = f"events/{meta['id']}_baseline.geojson"
        feature = {"type": "Feature", "properties": {"incident_id": meta["id"], **asdict(info)},
                   "geometry": footprint_geojson(geom_4326)}
        (data_dir / rel).write_text(json.dumps({"type": "FeatureCollection", "features": [feature]},
                                               separators=(",", ":")) + "\n")
        meta["baseline_path"] = rel
        report[meta["id"]] = {**asdict(info), "seconds": round(time.perf_counter() - start, 1)}
        print(f"{meta['id']}: {info.label()}  ({report[meta['id']]['seconds']} s)")

    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("data_dir", nargs="?", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--max-vertices", type=int, default=MAX_VERTICES)
    args = parser.parse_args()
    build(args.data_dir, args.max_vertices)
