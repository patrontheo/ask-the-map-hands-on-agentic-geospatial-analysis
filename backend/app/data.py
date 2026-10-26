import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]


class DataError(Exception):
    pass


@dataclass(frozen=True)
class Incident:
    id: str
    meta: dict
    polygons: gpd.GeoDataFrame  # EPSG:4326
    baseline: gpd.GeoDataFrame | None = None  # precomputed simplified footprint for the LLM-only baseline


@dataclass(frozen=True)
class Bundle:
    catalog: dict
    crs_projected: str
    sites: gpd.GeoDataFrame  # EPSG:4326, index site_id
    sites_projected: gpd.GeoSeries
    companies: pd.DataFrame  # index company_id
    districts: gpd.GeoDataFrame
    incidents: dict[str, Incident]
    buildings: gpd.GeoDataFrame | None = None
    parcels: gpd.GeoDataFrame | None = None


def load_bundle(data_dir: Path) -> Bundle:
    data_dir = Path(data_dir)
    catalog = json.loads((data_dir / "catalog.json").read_text())
    crs = catalog["crs_projected"]
    portfolio = catalog["portfolio"]

    df = pd.read_csv(data_dir / portfolio["sites"], dtype={"site_id": str, "company_id": str,
                                                           "district_code": str, "postcode": str})
    sites = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326")
    sites = sites.set_index("site_id", drop=False)
    companies = pd.read_csv(data_dir / portfolio["companies"], dtype=str).set_index("company_id", drop=False)
    districts = gpd.read_file(data_dir / catalog["districts"]).to_crs("EPSG:4326")

    incidents = {}
    for meta in catalog["incidents"]:
        polygons = gpd.read_file(data_dir / meta["path"]).to_crs("EPSG:4326")
        polygons = polygons[polygons.geometry.notna() & ~polygons.geometry.is_empty]
        if polygons.empty:
            raise DataError(f"incident {meta['id']} has no polygons")
        incidents[meta["id"]] = Incident(meta["id"], meta, polygons, _optional(data_dir, meta.get("baseline_path")))

    _validate(sites, companies, districts)
    return Bundle(
        catalog=catalog,
        crs_projected=crs,
        sites=sites,
        sites_projected=sites.geometry.to_crs(crs),
        companies=companies,
        districts=districts,
        incidents=incidents,
        buildings=_optional(data_dir, portfolio.get("buildings")),
        parcels=_optional(data_dir, portfolio.get("parcels")),
    )


def _optional(data_dir: Path, rel: str | None) -> gpd.GeoDataFrame | None:
    return gpd.read_file(data_dir / rel).to_crs("EPSG:4326") if rel else None


def _validate(sites, companies, districts):
    problems = []
    if sites.index.duplicated().any():
        problems.append(f"duplicate site_id: {sorted(sites.index[sites.index.duplicated()])}")
    if missing := sorted(set(sites.company_id) - set(companies.index)):
        problems.append(f"unknown company_id: {missing}")
    if missing := sorted(set(sites.district_code) - set(districts.district_code)):
        problems.append(f"unknown district_code: {missing}")
    tiv = sites[["tiv_building_eur", "tiv_contents_eur", "tiv_eur"]]
    if tiv.isna().any().any() or (tiv < 0).any().any():
        problems.append("TIV values must be present and >= 0")
    bad = (sites.tiv_eur - sites.tiv_building_eur - sites.tiv_contents_eur).abs() > 0.5
    if bad.any():
        problems.append(f"tiv_eur != building + contents for {sorted(sites.index[bad])}")
    if problems:
        raise DataError("; ".join(problems))


FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "bundle"


def data_dir() -> Path:
    # Until the real bundle is frozen, fall back to the test fixture so the app runs.
    if "DATA_DIR" in os.environ:
        return Path(os.environ["DATA_DIR"])
    real = REPO_ROOT / "data"
    return real if (real / "catalog.json").exists() else FIXTURE_DIR


@lru_cache(maxsize=1)
def get_bundle() -> Bundle:
    return load_bundle(data_dir())
