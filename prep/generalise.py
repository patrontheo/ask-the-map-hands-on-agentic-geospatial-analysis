"""Generalise a footprint to a vertex budget, so the model can read it whole.

Real EMS footprints are thousands of fragments (the Le Porge burnt area: 570k vertices, ~6M tokens).
Simplification alone can't meet the budget, so search combinations of a morphological closing (buffer
out then in, merging nearby fragments), dropping small parts, and Douglas-Peucker simplification, and
keep the one whose area differs least from the original. The result becomes the incident's footprint.
"""

from dataclasses import dataclass

import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

MAX_VERTICES = 3000  # about 13-20k tokens as GeoJSON with 5 decimals

PRE_TOLERANCE_M = 1.0
CLOSING_STEPS_M = [0, 15, 30, 60, 120]
MIN_PART_STEPS_M2 = [0, 2_000, 10_000, 50_000]
TOLERANCE_STEPS_M = [0, 5, 10, 20, 40, 80, 160]


@dataclass
class Generalisation:
    generalised: bool
    closing_m: float
    min_part_m2: float
    tolerance_m: float
    vertices_original: int
    vertices: int
    parts_original: int
    parts_kept: int
    area_differs_pct: float


def _parts(geom: BaseGeometry) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]


def _count(geom: BaseGeometry) -> int:
    return int(shapely.get_num_coordinates(geom))


def generalise(geom: BaseGeometry, max_vertices: int = MAX_VERTICES) -> tuple[BaseGeometry, Generalisation]:
    """Generalise a projected (metre) geometry to at most max_vertices. Takes minutes for real footprints."""
    original_parts = len(_parts(geom))
    if _count(geom) <= max_vertices:
        return geom, Generalisation(False, 0.0, 0.0, 0.0, _count(geom), _count(geom), original_parts,
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
    return result, Generalisation(
        generalised=True, closing_m=float(closing), min_part_m2=float(min_part),
        tolerance_m=float(max(tolerance, PRE_TOLERANCE_M)),
        vertices_original=_count(geom), vertices=_count(result), parts_original=original_parts,
        parts_kept=len(_parts(result)), area_differs_pct=float(error),
    )
