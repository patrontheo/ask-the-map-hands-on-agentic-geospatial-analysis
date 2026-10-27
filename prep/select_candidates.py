"""Pick candidate sites among IGN buildings in and around each incident footprint.

Reads sources/buildings-<incident>.gpkg (from fetch_ign.py) and writes work/candidates.csv,
the input of footprint_candidates.py. The site point is a point inside the building. About
three candidates per final site, so build_portfolio.py can drop ones the footprinter misses.
"""

import argparse
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely

from incidents import CRS_PROJECTED, INCIDENTS, SOURCES, WORK, footprint_projected

SEED = 20261103
EDGE_M = 30
NEAR_M = 2_000
FAR_M = 6_000
MIN_SPACING_M = 60
MIN_AREA_M2 = 150
SPREAD_CELL_M = 3_000

TARGETS = {"inside": 60, "edge_in": 12, "edge_out": 12, "near_out": 45, "far_out": 25}
USAGE_WEIGHT = {"Industriel": 4.0, "Commercial et services": 4.0, "Agricole": 2.0, "Indifférencié": 1.0}


def load_buildings(incident_id: str, sources: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(sources / f"buildings-{incident_id}.gpkg").to_crs(CRS_PROJECTED)
    if "etat_de_l_objet" in gdf.columns:
        gdf = gdf[gdf.etat_de_l_objet.fillna("En service") == "En service"]
    gdf = gdf[gdf.area >= MIN_AREA_M2].drop_duplicates("cleabs").reset_index(drop=True)
    points = gdf.geometry.representative_point()
    lon, lat = pyproj.Transformer.from_crs(CRS_PROJECTED, 4326, always_xy=True).transform(points.x.to_numpy(), points.y.to_numpy())
    return pd.DataFrame({
        "ign_building_id": gdf.cleabs, "ign_usage": gdf.usage_1, "x": points.x, "y": points.y, "lon": lon, "lat": lat,
    })


def classify(points: pd.DataFrame, footprint) -> pd.DataFrame:
    geoms = shapely.points(points.x.to_numpy(), points.y.to_numpy())
    parts = shapely.get_parts(footprint)
    (pt_idx, _), dist = shapely.STRtree(parts).query_nearest(geoms, return_distance=True, all_matches=False)
    to_footprint = np.full(len(geoms), np.inf)
    to_footprint[pt_idx] = dist
    (pt_idx, _), dist = shapely.STRtree(shapely.get_rings(parts)).query_nearest(geoms, return_distance=True, all_matches=False)
    to_boundary = np.full(len(geoms), np.inf)
    to_boundary[pt_idx] = dist

    out = points.copy()
    out["dist_to_footprint_m"] = to_footprint.round(1)
    out["dist_to_boundary_m"] = to_boundary.round(1)
    inside = to_footprint == 0
    out["zone_class"] = np.select(
        [inside & (to_boundary > EDGE_M), inside, to_footprint <= EDGE_M, to_footprint <= NEAR_M, to_footprint <= FAR_M],
        ["inside", "edge_in", "edge_out", "near_out", "far_out"],
        default="",
    )
    return out[out.zone_class != ""]


def sample(pool: pd.DataFrame, target: int, taken_xy: list, rng) -> pd.DataFrame:
    """Weighted sample without replacement, spread over grid cells, no two picks closer than MIN_SPACING_M."""
    if pool.empty:
        return pool
    weights = pool.ign_usage.map(USAGE_WEIGHT).fillna(1.0).to_numpy()
    keys = rng.random(len(pool)) ** (1.0 / weights)
    order = pool.iloc[np.argsort(-keys)]
    cap = max(3, math.ceil(target * 0.2))
    per_cell: dict[tuple, int] = {}
    picked = []
    for row in order.itertuples():
        if len(picked) >= target:
            break
        cell = (int(row.x // SPREAD_CELL_M), int(row.y // SPREAD_CELL_M))
        if per_cell.get(cell, 0) >= cap:
            continue
        if taken_xy and min(math.hypot(row.x - x, row.y - y) for x, y in taken_xy) < MIN_SPACING_M:
            continue
        picked.append(row.Index)
        taken_xy.append((row.x, row.y))
        per_cell[cell] = per_cell.get(cell, 0) + 1
    return pool.loc[picked]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default=str(SOURCES))
    parser.add_argument("--out", default=str(WORK / "candidates.csv"))
    args = parser.parse_args()

    rng = np.random.default_rng(SEED)
    taken_xy: list = []
    picks = []
    for incident_id in INCIDENTS:
        classified = classify(load_buildings(incident_id, Path(args.sources)), footprint_projected(incident_id))
        for zone_class, target in TARGETS.items():
            pool = classified[classified.zone_class == zone_class]
            chosen = sample(pool, target, taken_xy, rng)
            chosen.insert(0, "incident_id", incident_id)
            picks.append(chosen)
            print(f"{incident_id:22s} {zone_class:9s} pool {len(pool):>7,} picked {len(chosen):>3} "
                  f"by use {chosen.ign_usage.value_counts().to_dict()}")

    candidates = pd.concat(picks, ignore_index=True)
    candidates.insert(0, "candidate_id", [f"K{i:04d}" for i in range(1, len(candidates) + 1)])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(args.out, index=False)
    print(f"wrote {len(candidates)} candidates to {args.out}")


if __name__ == "__main__":
    main()
