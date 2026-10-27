"""Build the synthetic portfolio from footprinted candidate buildings.

Inputs: prep/work/{candidates.csv, candidate_buildings.geojson, candidate_parcels.geojson} (footprinter
site mode: several buildings and parcels per candidate) and prep/sources/communes.gpkg. Sites have
coordinates and a commune, no street address; address and postcode stay empty so the app's schema is unchanged.
Outputs: data/portfolio/{sites,companies}.csv, data/portfolio/{buildings,parcels}.geojson (one merged
polygon per site), data/admin/districts.geojson, and prep/out/edge_cases.json (organiser answer key).
"""

import json
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely

from incidents import CRS_PROJECTED, DATA, INCIDENTS, OUT, SOURCES, WORK, footprint_projected, footprint_wgs84
from select_candidates import classify

SEED = 20261103

# Sites per incident and zone class: 40 of 100 inside the footprint.
QUOTAS = {"inside": 35, "edge_in": 5, "edge_out": 2, "near_out": 40, "far_out": 18}
INSIDE_CLASSES = ("inside", "edge_in")

# (company_id, name, sector, sites, sites inside a footprint)
COMPANIES = [
    ("C01", "Halvorne Logistics", "Logistics", 12, 6),
    ("C02", "Corvanel Retail Group", "Retail", 10, 2),
    ("C03", "Duneveil Hospitality", "Hospitality", 9, 5),
    ("C04", "Ferlune Agri Services", "Agriculture", 8, 3),
    ("C05", "Quillmoor Engineering", "Manufacturing", 8, 3),
    ("C06", "Ardentis Office Partners", "Real estate", 7, 3),
    ("C07", "Velloran Foods", "Food processing", 7, 2),
    ("C08", "Brisemer Marine Supply", "Wholesale", 7, 4),
    ("C09", "Tarnwick Pharma", "Pharmaceuticals", 6, 1),
    ("C10", "Ombrelle Textiles", "Textiles", 6, 3),
    ("C11", "Kestrelon Data Services", "Technology", 5, 2),
    ("C12", "Lumivert Garden Centres", "Retail", 5, 1),
    ("C13", "Vinomarel Negoce", "Wine trading", 4, 2),
    ("C14", "Hollin & Sparre Notaires", "Professional services", 3, 0),
    ("C15", "Saltmarrow Campings", "Hospitality", 3, 3),
]
TOP_ABSOLUTE = "C01"
ALL_INSIDE, NONE_INSIDE = "C15", "C14"
TIE_PAIR = ("C05", "C06")
ZERO_TIV_COMPANY = "C07"
VERTEX_INCIDENT = "wildfire_leporge_2026"

# Reconstruction cost EUR/m2 of floor area, and contents as a share of building value.
BUILDING_RATE = {"office": 1800, "retail": 1400, "hotel": 2000, "industrial": 900, "warehouse": 650, "agricultural": 400}
CONTENTS_RATIO = {"office": 0.35, "retail": 0.6, "hotel": 0.3, "industrial": 0.8, "warehouse": 1.0, "agricultural": 0.5}
MAX_FLOOR_AREA_M2 = 40_000
USAGE_SCORE = {"Industriel": 3, "Commercial et services": 3, "Agricole": 3, "Indifférencié": 2}


def property_type(usage: str, area_m2: float, floors: int, draw: float, nature: str = "") -> str:
    if nature == "Serre":
        return "agricultural"
    if usage == "Industriel":
        return "warehouse" if area_m2 >= 2000 else "industrial"
    if usage == "Agricole":
        return "agricultural"
    if usage == "Commercial et services":
        if floors >= 3:
            return "office" if draw < 0.8 else "hotel"
        return "retail" if draw < 0.55 else ("office" if draw < 0.85 else "hotel")
    if usage == "Indifférencié":  # mostly sheds and outbuildings, e.g. in the Médoc forest
        return "agricultural" if draw < 0.5 else "warehouse"
    return "retail" if draw < 0.6 else "office"


def floors_of(row) -> int:
    if pd.notna(row.get("nombre_d_etages")) and row["nombre_d_etages"] > 0:
        return int(min(row["nombre_d_etages"], 8))
    if pd.notna(row.get("hauteur")) and row["hauteur"] > 0:
        return int(min(max(1, round(row["hauteur"] / 3.5)), 8))
    return 1


def with_point_flag(gdf: gpd.GeoDataFrame, cand: pd.DataFrame) -> gpd.GeoDataFrame:
    """Flag the rows whose geometry covers their candidate's site point."""
    pts = cand.set_index("candidate_id")
    points = gpd.points_from_xy(pts.loc[gdf.candidate_id, "lon"], pts.loc[gdf.candidate_id, "lat"])
    return gdf.assign(covers_point=shapely.covers(gdf.geometry.values, points))


def load_candidates() -> gpd.GeoDataFrame:
    """One row per candidate site: all its buildings and parcels merged (footprinter site mode)."""
    cand = pd.read_csv(WORK / "candidates.csv", dtype={"ign_building_id": str})
    # Bands are recomputed against the footprint in data/events, which may have changed since selection.
    cand = pd.concat([classify(cand[cand.incident_id == i], footprint_projected(i)) for i in INCIDENTS])
    bld = gpd.read_file(WORK / "candidate_buildings.geojson")
    par = gpd.read_file(WORK / "candidate_parcels.geojson")
    bld, par = bld[bld.candidate_id.isin(cand.candidate_id)], par[par.candidate_id.isin(cand.candidate_id)]
    for col in ("nombre_d_etages", "hauteur", "area_m2"):  # IGN returns some numbers as text
        if col in bld.columns:
            bld[col] = pd.to_numeric(bld[col], errors="coerce")
    if "code_insee" in par.columns:
        par["parcel_commune"] = par.code_insee.astype(str)
    elif {"code_dep", "code_com"} <= set(par.columns):
        par["parcel_commune"] = par.code_dep.astype(str) + par.code_com.astype(str).str.zfill(3)
    else:
        par["parcel_commune"] = None

    # Storeys per building: the recorded count, else from height (offices, shops) or 1 (sheds, high-bay halls).
    explicit = bld.get("nombre_d_etages", pd.Series(np.nan, index=bld.index)).where(lambda s: s > 0).clip(upper=8)
    from_height = (bld.get("hauteur", pd.Series(np.nan, index=bld.index)) / 3.5).round().clip(1, 8).fillna(1)
    bld["floor_area_tall"] = bld.area_m2 * explicit.fillna(from_height)
    bld["floor_area_sheds"] = bld.area_m2 * explicit.fillna(1)

    # The main building is the one under the site point; it decides the property type.
    bld = with_point_flag(bld, cand)
    main = bld.sort_values(["candidate_id", "covers_point", "area_m2"], ascending=[True, False, False]).drop_duplicates("candidate_id")
    main_cols = [c for c in ("candidate_id", "cleabs", "usage_1", "nature", "nombre_d_etages", "hauteur") if c in main.columns]
    totals = bld.groupby("candidate_id").agg(building_count=("area_m2", "size"), building_area_m2=("area_m2", "sum"),
                                             floor_area_tall=("floor_area_tall", "sum"), floor_area_sheds=("floor_area_sheds", "sum"))
    site_bld = bld[["candidate_id", "geometry"]].dissolve("candidate_id").join(totals)
    site_bld = site_bld.join(main[main_cols].set_index("candidate_id")).reset_index()

    par = with_point_flag(par, cand)
    main_par = par.sort_values(["candidate_id", "covers_point"], ascending=[True, False]).drop_duplicates("candidate_id")
    site_par = par[["candidate_id", "geometry"]].dissolve("candidate_id").rename_geometry("parcel_geometry")
    site_par = site_par.join(par.groupby("candidate_id").agg(parcel_count=("geometry", "size"), parcel_area_m2=("area_m2", "sum")))
    site_par = site_par.join(main_par.set_index("candidate_id")[["idu", "parcel_commune"]]).reset_index()

    merged = cand.merge(pd.DataFrame(site_bld), on="candidate_id", how="inner")
    merged = merged.merge(pd.DataFrame(site_par), on="candidate_id", how="inner")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)


def score_candidates(cand: gpd.GeoDataFrame, rng) -> gpd.GeoDataFrame:
    cand = cand.copy()
    cand["point_inside"] = False
    cand["building_disagrees"] = False
    for incident_id in INCIDENTS:
        fp = footprint_projected(incident_id)
        mask = cand.incident_id == incident_id
        sub = cand[mask]
        pts = gpd.GeoSeries(gpd.points_from_xy(sub.x, sub.y), crs=CRS_PROJECTED)
        blds = sub.geometry.to_crs(CRS_PROJECTED)
        inside = shapely.covers(fp, pts.values)
        bld_any = shapely.intersects(fp, blds.values)
        bld_all = shapely.covers(fp, blds.values)
        cand.loc[mask, "point_inside"] = inside
        cand.loc[mask, "building_disagrees"] = (inside & ~bld_all) | (~inside & bld_any)
    cand["usage_1"] = cand["usage_1"].fillna(cand["ign_usage"])
    cand["score"] = (
        cand["usage_1"].map(USAGE_SCORE).fillna(1) * 10
        + (cand["zone_class"].str.startswith("edge") & cand["building_disagrees"]) * 20
        + rng.random(len(cand))
    )
    return cand


def select_sites(cand: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    fill_from = {"edge_in": "inside", "inside": "edge_in", "edge_out": "near_out", "near_out": "far_out", "far_out": "near_out"}
    # Site mode can expand two candidates on one estate to the same parcels: keep only the first of them.
    parcels = gpd.GeoSeries(cand.parcel_geometry.values, index=cand.index, crs=4326).to_crs(CRS_PROJECTED)
    taken: list = []

    def free(idx) -> bool:
        return all(parcels[idx].intersection(other).area <= 1 for other in taken)

    picked = []
    for incident_id in INCIDENTS:
        pool = cand[cand.incident_id == incident_id].sort_values("score", ascending=False)
        used: set = set()
        for zone_class, quota in QUOTAS.items():
            take = []
            for cls in (zone_class, fill_from[zone_class]):
                for idx in pool.index[(pool.zone_class == cls) & ~pool.candidate_id.isin(used)]:
                    if len(take) >= quota:
                        break
                    if free(idx):
                        take.append(idx)
                        taken.append(parcels[idx])
                        used.add(pool.at[idx, "candidate_id"])
                if len(take) >= quota:
                    break
                print(f"WARNING {incident_id} {zone_class}: {len(take)}/{quota}, filling from {fill_from[zone_class]}")
            picked.append(pool.loc[take])
    sites = pd.concat(picked)
    sites["is_inside"] = sites.zone_class.isin(INSIDE_CLASSES)
    return gpd.GeoDataFrame(sites, geometry="geometry", crs=4326)


def assign_companies(sites: gpd.GeoDataFrame, rng) -> gpd.GeoDataFrame:
    sites = sites.copy()
    sites["company_id"] = ""
    pools = {}
    for (incident_id, is_inside), group in sites.groupby(["incident_id", "is_inside"]):
        idx = list(group.index)
        rng.shuffle(idx)
        pools[(incident_id, bool(is_inside))] = idx
    incidents = list(INCIDENTS)
    for company_id, _, _, n_sites, n_inside in COMPANIES:
        region = int(rng.integers(len(incidents)))
        for is_inside, count in ((True, n_inside), (False, n_sites - n_inside)):
            for _ in range(count):
                for attempt in range(len(incidents)):
                    key = (incidents[(region + attempt) % len(incidents)], is_inside)
                    if pools.get(key):
                        sites.loc[pools[key].pop(), "company_id"] = company_id
                        break
                else:
                    raise RuntimeError(f"ran out of {'inside' if is_inside else 'outside'} sites for {company_id}")
                region += 1
    assert (sites.company_id != "").all(), "every selected site must belong to a company"
    return sites


def set_tiv(sites: gpd.GeoDataFrame, rng) -> gpd.GeoDataFrame:
    sites = sites.copy()
    types, building, contents = [], [], []
    for _, row in sites.iterrows():
        usage = row["usage_1"] if isinstance(row["usage_1"], str) else ""
        nature = row["nature"] if isinstance(row.get("nature"), str) else ""
        ptype = property_type(usage, float(row["building_area_m2"]), floors_of(row), rng.random(), nature)
        # Floor area summed over all buildings on the site; sheds and high-bay halls count as single storey.
        sheds = ptype in ("industrial", "warehouse", "agricultural")
        floor_area = min(float(row["floor_area_sheds"] if sheds else row["floor_area_tall"]), MAX_FLOOR_AREA_M2)
        value = max(100_000, floor_area * BUILDING_RATE[ptype] * rng.lognormal(0, 0.25))
        types.append(ptype)
        building.append(round(value, -3))
        contents.append(round(value * CONTENTS_RATIO[ptype] * rng.lognormal(0, 0.2), -3))
    sites["property_type"] = types
    sites["tiv_building_eur"] = np.array(building, dtype=np.int64)
    sites["tiv_contents_eur"] = np.array(contents, dtype=np.int64)

    zero_idx = sites[(sites.company_id == ZERO_TIV_COMPANY) & sites.is_inside].index[0]
    sites.loc[zero_idx, ["tiv_building_eur", "tiv_contents_eur"]] = 0

    exposed = lambda: sites[sites.is_inside].groupby("company_id")[["tiv_building_eur", "tiv_contents_eur"]].sum().sum(axis=1)
    top_other = exposed().drop(TOP_ABSOLUTE).max()
    if exposed()[TOP_ABSOLUTE] <= top_other:
        factor = top_other / exposed()[TOP_ABSOLUTE] * 1.3
        mask = (sites.company_id == TOP_ABSOLUTE) & sites.is_inside
        for col in ("tiv_building_eur", "tiv_contents_eur"):
            sites.loc[mask, col] = (sites.loc[mask, col] * factor).round(-3).astype(np.int64)

    a, b = TIE_PAIR
    delta = int(exposed()[a] - exposed()[b])
    target = b if delta > 0 else a
    big = sites[(sites.company_id == target) & sites.is_inside & (sites.tiv_building_eur > 0)].sort_values("tiv_building_eur").index[-1]
    sites.loc[big, "tiv_building_eur"] += abs(delta)

    sites["tiv_eur"] = sites.tiv_building_eur + sites.tiv_contents_eur
    return sites


def snap_vertex_site(sites: gpd.GeoDataFrame) -> dict:
    """Move one near-edge flood site onto a footprint vertex: the boundary-inclusion edge case."""
    fp4326 = footprint_wgs84(VERTEX_INCIDENT)
    fp2154 = footprint_projected(VERTEX_INCIDENT)
    to2154 = pyproj.Transformer.from_crs(4326, CRS_PROJECTED, always_xy=True)
    vertices = shapely.points(shapely.get_coordinates(shapely.get_exterior_ring(shapely.get_parts(fp4326))))
    candidates = sites[(sites.incident_id == VERTEX_INCIDENT) & (sites.zone_class == "edge_in")]
    for idx, row in candidates.iterrows():
        here = shapely.Point(row.lon, row.lat)
        near = vertices[np.argmin(shapely.distance(vertices, here))]
        x, y = to2154.transform(near.x, near.y)
        moved = math.hypot(x - row.x, y - row.y)
        if moved <= 40 and fp2154.covers(shapely.Point(x, y)) and fp2154.boundary.distance(shapely.Point(x, y)) < 1e-6:
            sites.loc[idx, ["lon", "lat", "x", "y"]] = [near.x, near.y, x, y]
            return {"site_index": idx, "moved_m": round(moved, 1)}
    raise RuntimeError("no edge_in flood site has a footprint vertex within 40 m")


def assign_districts(sites: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, list]:
    """District = commune polygon covering the site point, cross-checked against the parcel's commune code."""
    communes = gpd.read_file(SOURCES / "communes.gpkg").to_crs(CRS_PROJECTED)
    communes["district_code"] = communes.district_code.astype(str)
    pts = gpd.GeoDataFrame({"row": sites.index}, geometry=gpd.points_from_xy(sites.x, sites.y), crs=CRS_PROJECTED)
    joined = gpd.sjoin(pts, communes[["district_code", "district_name", "geometry"]], how="left", predicate="intersects")
    joined = joined.sort_values("district_code").drop_duplicates("row").set_index("row")
    missing = joined.district_code.isna()
    if missing.any():
        raise RuntimeError(f"no commune polygon for sites {sites.loc[joined.index[missing], 'site_id'].tolist()}")
    sites = sites.copy()
    sites["district_code"] = joined.district_code.reindex(sites.index)
    sites["district_name"] = joined.district_name.reindex(sites.index)
    check = sites.parcel_commune.notna()
    bad = sites[check & (sites.parcel_commune.astype(str) != sites.district_code)]
    mismatches = bad[["site_id", "district_code", "parcel_commune"]].to_dict("records")
    used = communes[communes.district_code.isin(sites.district_code)][["district_code", "district_name", "geometry"]]
    return sites, used.to_crs(4326).reset_index(drop=True), mismatches


def main() -> None:
    rng = np.random.default_rng(SEED)
    cand = score_candidates(load_candidates(), rng)
    sites = select_sites(cand)
    sites = assign_companies(sites, rng)

    order = list(sites.index)
    rng.shuffle(order)
    sites = sites.loc[order].reset_index(drop=True)
    n = len(sites)
    sites["site_id"] = [f"S{i:03d}" for i in range(1, n + 1)]
    sites["building_id"] = [f"B{i:03d}" for i in range(1, n + 1)]
    sites["parcel_id"] = [f"P{i:03d}" for i in range(1, n + 1)]

    to2154 = pyproj.Transformer.from_crs(4326, CRS_PROJECTED, always_xy=True)
    sites["x"], sites["y"] = to2154.transform(sites.lon.to_numpy(), sites.lat.to_numpy())
    vertex = snap_vertex_site(sites)
    sites = set_tiv(sites, rng)

    sites, districts, mismatches = assign_districts(sites)
    sites["address"] = ""
    sites["postcode"] = ""
    sites["city"] = sites.district_name
    # IDs differ by design (WFS feature id vs BD TOPO cleabs), so compare geometry: is the site point in its building?
    site_points = gpd.points_from_xy(sites.lon, sites.lat)
    point_outside_building = sites.site_id[~shapely.covers(sites.geometry.values, site_points)].tolist()

    DATA.joinpath("portfolio").mkdir(parents=True, exist_ok=True)
    DATA.joinpath("admin").mkdir(parents=True, exist_ok=True)
    columns = ["site_id", "company_id", "address", "postcode", "city", "district_code", "district_name", "property_type",
               "lon", "lat", "x", "y", "tiv_building_eur", "tiv_contents_eur", "tiv_eur", "building_id", "parcel_id"]
    # Full float precision: rounding would move the vertex site off the footprint boundary.
    sites[columns].to_csv(DATA / "portfolio/sites.csv", index=False)
    pd.DataFrame([c[:3] for c in COMPANIES], columns=["company_id", "company_name", "sector"]).to_csv(DATA / "portfolio/companies.csv", index=False)

    buildings = gpd.GeoDataFrame(
        sites[["building_id", "site_id", "ign_building_id", "usage_1", "building_count", "building_area_m2"]].rename(
            columns={"ign_building_id": "source_id"}),
        geometry=sites.geometry.values, crs=4326,
    )
    buildings["source"] = "IGN BD TOPO via footprinter"
    buildings.to_file(DATA / "portfolio/buildings.geojson", driver="GeoJSON")
    parcels = gpd.GeoDataFrame(
        sites[["parcel_id", "site_id", "idu", "parcel_count", "parcel_area_m2"]].rename(columns={"idu": "source_id"}),
        geometry=sites.parcel_geometry.values, crs=4326,
    )
    parcels["source"] = "IGN Parcellaire Express (PCI) via footprinter"
    parcels.to_file(DATA / "portfolio/parcels.geojson", driver="GeoJSON")
    districts.to_file(DATA / "admin/districts.geojson", driver="GeoJSON")

    report = verify(sites)
    report["vertex_site"] = {"site_id": sites.loc[vertex["site_index"], "site_id"], "incident_id": VERTEX_INCIDENT,
                             "moved_from_building_point_m": vertex["moved_m"]}
    report["district_mismatches_polygon_vs_parcel"] = mismatches
    report["site_point_outside_its_building"] = point_outside_building
    OUT.mkdir(exist_ok=True)
    (OUT / "edge_cases.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(report["summary"], indent=2))
    print(f"district mismatches (commune polygon vs parcel): {len(mismatches)}; "
          f"site point outside its building: {point_outside_building} (the vertex site is expected here)")


def verify(sites: gpd.GeoDataFrame) -> dict:
    """Recompute inclusion from scratch and check every curated edge case."""
    pts = gpd.GeoSeries(gpd.points_from_xy(sites.x, sites.y), crs=CRS_PROJECTED).values
    inside_any = np.zeros(len(sites), dtype=bool)
    per_incident = {}
    for incident_id in INCIDENTS:
        covered = shapely.covers(footprint_projected(incident_id), pts)
        per_incident[incident_id] = sites.site_id[covered].tolist()
        inside_any |= covered
    assert (inside_any == sites.is_inside.to_numpy()).all(), "recomputed inclusion differs from the selection"

    s = sites.assign(inside=inside_any)
    total = s.groupby("company_id").tiv_eur.sum()
    exposed = s[s.inside].groupby("company_id").tiv_eur.sum().reindex(total.index, fill_value=0)
    share = (exposed / total).fillna(0)
    rank = lambda m: sorted(m.index, key=lambda c: (-m[c], c))

    counts = s.groupby("company_id").agg(sites=("site_id", "size"), inside=("inside", "sum"))
    assert counts.sites.between(3, 12).all()
    assert counts.loc[ALL_INSIDE, "inside"] == counts.loc[ALL_INSIDE, "sites"]
    assert counts.loc[NONE_INSIDE, "inside"] == 0
    assert rank(exposed)[0] == TOP_ABSOLUTE and rank(share)[0] != TOP_ABSOLUTE
    assert exposed[TIE_PAIR[0]] == exposed[TIE_PAIR[1]]
    assert ((s.tiv_eur == 0) & s.inside).sum() == 1
    assert (s.tiv_eur == s.tiv_building_eur + s.tiv_contents_eur).all() and (s.tiv_eur >= 0).all()
    parcels = gpd.GeoSeries(s.parcel_geometry.values, crs=4326).to_crs(CRS_PROJECTED)
    left, right = shapely.STRtree(parcels.values).query(parcels.values, predicate="intersects")
    shared = [(s.site_id.iloc[a], s.site_id.iloc[b]) for a, b in zip(left, right)
              if a < b and parcels.iloc[a].intersection(parcels.iloc[b]).area > 1]
    assert not shared, f"sites share parcels: {shared}"

    edge = s[s.zone_class.str.startswith("edge")]
    return {
        "summary": {
            "sites": len(s), "inside": int(s.inside.sum()), "inside_share_pct": round(100 * s.inside.mean(), 1),
            "inside_per_incident": {k: len(v) for k, v in per_incident.items()},
            "property_types": s.property_type.value_counts().to_dict(),
            "top_by_exposed_tiv": rank(exposed)[:3], "top_by_exposed_share": rank(share)[:3],
        },
        "selected_site_ids": per_incident,
        "company_exposure": [
            {"company_id": c, "sites": int(counts.loc[c, "sites"]), "inside": int(counts.loc[c, "inside"]),
             "exposed_tiv_eur": int(exposed[c]), "total_tiv_eur": int(total[c]), "share_pct": round(100 * share[c], 1)}
            for c in total.index
        ],
        "all_inside_company": ALL_INSIDE,
        "no_inside_company": NONE_INSIDE,
        "tie": {"companies": list(TIE_PAIR), "exposed_tiv_eur": int(exposed[TIE_PAIR[0]])},
        "zero_tiv_site": s[(s.tiv_eur == 0) & s.inside].site_id.tolist(),
        "near_edge_sites": edge[["site_id", "incident_id", "zone_class", "building_disagrees"]].to_dict("records"),
    }


if __name__ == "__main__":
    main()
