"""LLM-only baseline: the same data and definitions as the tool path, put in the prompt, with no tools.

Real footprints are far too large for a prompt, so the baseline gets a simplified footprint, labelled as
such. The tools always use the full footprint.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.geometry.base import BaseGeometry

from backend.app.analysis import incident_footprint
from backend.app.data import Bundle
from backend.app.tools.core import DEFINITIONS

PROMPT = (Path(__file__).parent / "prompts" / "baseline.md").read_text()
SITE_COLUMNS = ["site_id", "company_id", "address", "postcode", "city", "district_code", "district_name",
                "property_type", "lon", "lat", "tiv_building_eur", "tiv_contents_eur", "tiv_eur"]
MAX_VERTICES = int(os.environ.get("BASELINE_MAX_VERTICES", "3000"))
COORD_DECIMALS = 5  # about 1 m in EPSG:4326


@dataclass
class SimplificationInfo:
    simplified: bool
    closing_m: float
    min_part_m2: float
    tolerance_m: float
    vertices_original: int
    vertices: int
    parts_original: int
    parts_kept: int
    area_differs_pct: float
    sites_differ: int | None = None  # filled in by prep/ once the portfolio exists
    sites_total: int | None = None

    def label(self) -> str:
        if not self.simplified:
            return "Full footprint (small enough to include unchanged)."
        text = (f"SIMPLIFIED footprint, not the one the tools use: gaps up to {2 * self.closing_m:g} m closed, "
                f"parts under {self.min_part_m2:,.0f} m² dropped, edges simplified with a {self.tolerance_m:g} m "
                f"tolerance; {self.vertices:,} of {self.vertices_original:,} vertices and {self.parts_kept:,} of "
                f"{self.parts_original:,} polygon parts remain; {self.area_differs_pct:.1f} % of the area differs "
                f"from the full footprint.")
        if self.sites_differ is not None:
            text += (f" Against the full footprint, {self.sites_differ} of {self.sites_total} portfolio sites "
                     f"would be classified differently.")
        return text + " Sites near the edge may be classified differently than with the full footprint."


def _parts(geom: BaseGeometry) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]


PRE_TOLERANCE_M = 1.0
CLOSING_STEPS_M = [0, 15, 30, 60, 120]
MIN_PART_STEPS_M2 = [0, 2_000, 10_000, 50_000]
TOLERANCE_STEPS_M = [0, 5, 10, 20, 40, 80, 160]


def _count(geom: BaseGeometry) -> int:
    return int(shapely.get_num_coordinates(geom))


def simplify_to_budget(geom: BaseGeometry, max_vertices: int) -> tuple[BaseGeometry, SimplificationInfo]:
    """Generalise a projected (metre) geometry to at most max_vertices, keeping it as close as possible.

    Real footprints are thousands of fragments, so simplification alone can't meet the budget. Search
    combinations of a morphological closing (buffer out then in, merging nearby fragments), dropping small
    parts, and Douglas-Peucker simplification; keep the one whose area differs least from the original.
    For large footprints this takes minutes, so prep/ precomputes it.
    """
    original_parts = len(_parts(geom))
    if _count(geom) <= max_vertices:
        return geom, SimplificationInfo(False, 0.0, 0.0, 0.0, _count(geom), _count(geom), original_parts,
                                        original_parts, 0.0)

    pre = geom.simplify(PRE_TOLERANCE_M, preserve_topology=True)  # drops near-collinear vertices, speeds up search
    best = None
    for closing in CLOSING_STEPS_M:
        closed = pre if closing == 0 else pre.buffer(closing).buffer(-closing)
        for min_part in MIN_PART_STEPS_M2:
            parts = [p for p in _parts(closed) if p.area >= min_part]
            if not parts:
                continue
            filtered = MultiPolygon(parts) if len(parts) > 1 else parts[0]
            for tolerance in TOLERANCE_STEPS_M:
                candidate = filtered if tolerance == 0 else filtered.simplify(tolerance, preserve_topology=True)
                if _count(candidate) <= max_vertices:
                    error = geom.symmetric_difference(candidate).area / geom.area * 100 if geom.area else 0.0
                    if best is None or error < best[0]:
                        best = (error, candidate, closing, min_part, tolerance)
                    break
    if best is None:
        raise ValueError(f"no generalisation fits {max_vertices} vertices; raise the budget")

    error, result, closing, min_part, tolerance = best
    return result, SimplificationInfo(
        simplified=True, closing_m=float(closing), min_part_m2=float(min_part),
        tolerance_m=float(max(tolerance, PRE_TOLERANCE_M)),
        vertices_original=_count(geom), vertices=_count(result), parts_original=original_parts,
        parts_kept=len(_parts(result)), area_differs_pct=float(error),
    )


_footprints: dict[tuple[int, str], tuple[BaseGeometry, SimplificationInfo]] = {}


def _plain(value):
    """NumPy scalars from GeoDataFrame rows to Python values; NaN (missing optional field) to None."""
    value = value.item() if hasattr(value, "item") else value
    if isinstance(value, float):
        if value != value:
            return None
        if value.is_integer():  # integer columns with missing values come back as floats
            return int(value)
    return value


def baseline_footprint(bundle: Bundle, incident_id: str) -> tuple[BaseGeometry, SimplificationInfo]:
    """Simplified footprint in EPSG:4326, cached per bundle.

    Real incidents ship a precomputed file (catalog `baseline_path`, written by prep/); generalising them
    takes minutes. Small footprints, such as the test fixture, are handled at runtime.
    """
    key = (id(bundle), incident_id)
    if key not in _footprints:
        incident = bundle.incidents[incident_id]
        if incident.baseline is not None:
            row = incident.baseline.iloc[0]
            fields = {f: _plain(row[f]) for f in SimplificationInfo.__dataclass_fields__ if f in row.index}
            _footprints[key] = (row.geometry, SimplificationInfo(**fields))
        else:
            projected, info = simplify_to_budget(incident_footprint(bundle, incident_id).union_projected, MAX_VERTICES)
            geom_4326 = gpd.GeoSeries([projected], crs=bundle.crs_projected).to_crs("EPSG:4326").iloc[0]
            _footprints[key] = (geom_4326, info)
    return _footprints[key]


def footprint_geojson(geom: BaseGeometry) -> dict:
    def rounded(coords):
        if isinstance(coords[0], (int, float)):
            return [round(c, COORD_DECIMALS) for c in coords]
        return [rounded(c) for c in coords]

    g = mapping(geom)
    return {"type": g["type"], "coordinates": rounded(g["coordinates"])}


_instructions: dict[int, str] = {}


def baseline_instructions(bundle: Bundle) -> str:
    if id(bundle) not in _instructions:
        _instructions[id(bundle)] = _build(bundle)
    return _instructions[id(bundle)]


def baseline_footprint_info(bundle: Bundle) -> dict[str, dict]:
    return {i: asdict(baseline_footprint(bundle, i)[1]) for i in bundle.incidents}


def _build(bundle: Bundle) -> str:
    sites = bundle.sites[SITE_COLUMNS].to_csv(index=False)
    companies = bundle.companies[["company_id", "company_name"]].to_csv(index=False)
    footprints = []
    for incident in bundle.incidents.values():
        geom, info = baseline_footprint(bundle, incident.id)
        geojson = json.dumps(footprint_geojson(geom), separators=(",", ":"))
        footprints.append(f"### Incident `{incident.id}` ({incident.meta.get('peril')}, "
                          f"{incident.meta.get('name')}, {incident.meta.get('date')})\n"
                          f"{info.label()}\nGeoJSON geometry, EPSG:4326 (lon, lat):\n{geojson}")
    definitions = "\n".join(f"- **{k}**: {v}" for k, v in DEFINITIONS.items())
    return "\n\n".join([
        PROMPT,
        f"## Definitions\n{definitions}\n- Coordinates are EPSG:4326; metric work is defined in "
        f"{bundle.crs_projected}.",
        f"## Sites ({len(bundle.sites)} rows, CSV)\n{sites}",
        f"## Companies (CSV)\n{companies}",
        "## Incident footprints\n" + "\n\n".join(footprints),
    ])
