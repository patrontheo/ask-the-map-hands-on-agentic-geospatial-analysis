"""Deterministic spatial screening functions. Pure: no I/O, no model."""

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from shapely import make_valid
from shapely.geometry.base import BaseGeometry

from backend.app.data import Bundle

GroupBy = Literal["none", "company", "district", "property_type"]
Metric = Literal["n_sites", "tiv"]
TIV_MEASURE = "sum of tiv_eur (building + contents, EUR, no BI)"


class AnalysisError(Exception):
    def __init__(self, code: str, message: str, hint: str = ""):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


@dataclass
class Footprint:
    incident_id: str
    union_projected: BaseGeometry
    n_polygons: int
    bbox_4326: list[float]
    meta: dict


@dataclass
class Selection:
    site_ids: list[str]
    n_sites: int
    metadata: dict


@dataclass
class Summary:
    table: pd.DataFrame
    metadata: dict = field(default_factory=dict)


@dataclass
class Distance:
    distance_m: float
    crs: str
    method: str = "straight line in projected CRS"


_footprints: dict[tuple[int, str], Footprint] = {}


def incident_footprint(bundle: Bundle, incident_id: str) -> Footprint:
    """Union of the incident's polygons in the projected CRS; cached because real footprints take seconds."""
    incident = bundle.incidents.get(incident_id)
    if incident is None:
        raise AnalysisError("unknown_incident", f"Unknown incident_id '{incident_id}'.",
                            f"Valid incident_id values: {', '.join(sorted(bundle.incidents))}.")
    key = (id(bundle), incident_id)
    if key not in _footprints:
        _footprints[key] = _build_footprint(bundle, incident)
    return _footprints[key]


def _build_footprint(bundle: Bundle, incident) -> Footprint:
    incident_id = incident.id
    projected = incident.polygons.geometry.to_crs(bundle.crs_projected).map(make_valid)
    return Footprint(
        incident_id=incident_id,
        union_projected=projected.union_all(),
        n_polygons=len(projected),
        bbox_4326=[float(v) for v in incident.polygons.total_bounds],
        meta=incident.meta,
    )


def select_sites_in_incident(bundle: Bundle, incident_id: str) -> Selection:
    fp = incident_footprint(bundle, incident_id)
    if bundle.buildings is not None:
        buildings = bundle.buildings.to_crs(bundle.crs_projected)
        if "site_id" not in buildings:
            raise AnalysisError("invalid_dataset", "Building geometry must have a site_id column.",
                                "Link each building to its portfolio site.")
        affected = buildings.geometry.map(make_valid).intersects(fp.union_projected)
        site_ids = sorted(set(buildings.loc[affected, "site_id"]))
        check_site_ids(bundle, site_ids)
        basis = "building_intersection"
        predicate = "intersects (any building; boundary contact included)"
    else:
        # Tiny teaching fixtures have no buildings; make the point approximation explicit.
        inside = bundle.sites_projected.map(fp.union_projected.covers)
        site_ids = sorted(bundle.sites_projected.index[inside.astype(bool)])
        basis = "point_fallback"
        predicate = "covers (point fallback; no building dataset)"
    return Selection(site_ids, len(site_ids), {
        "incident_id": incident_id,
        "predicate": predicate,
        "selection_basis": basis,
        "crs": bundle.crs_projected,
        "n_footprint_polygons": fp.n_polygons,
        "footprint_date": fp.meta.get("date"),
        "source": fp.meta.get("source"),
    })


def check_site_ids(bundle: Bundle, site_ids: list[str]) -> None:
    unknown = [s for s in site_ids if s not in bundle.sites.index]
    if unknown:
        raise AnalysisError("unknown_site_ids", f"{len(unknown)} unknown site_id(s).",
                            f"Unknown: {', '.join(unknown[:5])}. Site IDs look like '{bundle.sites.index[0]}'.")


def summarize_sites(bundle: Bundle, site_ids: list[str] | None, group_by: GroupBy = "none",
                    metric: Metric = "tiv") -> Summary:
    if site_ids is None:
        distinct = list(bundle.sites.index)
        n_input = len(distinct)
    else:
        check_site_ids(bundle, site_ids)
        distinct = list(dict.fromkeys(site_ids))
        n_input = len(site_ids)

    sites = pd.DataFrame(bundle.sites.loc[distinct].drop(columns="geometry"))
    key = {"none": None, "company": "company_id", "district": "district_code",
           "property_type": "property_type"}[group_by]
    sites["group"] = "all" if key is None else sites[key]
    table = (sites.groupby("group", as_index=False)
             .agg(n_sites=("site_id", "size"), tiv_eur=("tiv_eur", "sum")))
    table["group_name"] = table["group"].map(_group_names(bundle, group_by))
    sort_col = "tiv_eur" if metric == "tiv" else "n_sites"
    table = table.sort_values([sort_col, "group"], ascending=[False, True], kind="stable")
    table = table[["group", "group_name", "n_sites", "tiv_eur"]].reset_index(drop=True)

    return Summary(table, {
        "group_by": group_by,
        "metric": metric,
        "measure": TIV_MEASURE if metric == "tiv" else "count of distinct sites",
        "n_input_ids": n_input,
        "n_distinct_sites": len(distinct),
        "duplicates_removed": n_input - len(distinct),
        "total_tiv_eur": float(table.tiv_eur.sum()),
        "total_sites": int(table.n_sites.sum()),
    })


def _group_names(bundle: Bundle, group_by: GroupBy) -> dict:
    if group_by == "company":
        return bundle.companies.company_name.to_dict()
    if group_by == "district":
        return dict(zip(bundle.districts.district_code, bundle.districts.district_name))
    if group_by == "property_type":
        return {v: v for v in bundle.sites.property_type.unique()}
    return {"all": "All selected sites"}


def distance_between_sites(bundle: Bundle, site_a: str, site_b: str) -> Distance:
    check_site_ids(bundle, [site_a, site_b])
    d = bundle.sites_projected[site_a].distance(bundle.sites_projected[site_b])
    return Distance(round(float(d), 1), bundle.crs_projected)
