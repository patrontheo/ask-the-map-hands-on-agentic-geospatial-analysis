"""Incident footprint geometry as GeoJSON for the model to read.

Footprints in data/ are prepared small enough to read whole (prep/build_events.py), so no
simplification happens here.
"""

from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

COORD_DECIMALS = 5  # about 1 m in EPSG:4326


def footprint_geojson(geom: BaseGeometry) -> dict:
    def rounded(coords):
        if isinstance(coords[0], (int, float)):
            return [round(c, COORD_DECIMALS) for c in coords]
        return [rounded(c) for c in coords]

    g = mapping(geom)
    return {"type": g["type"], "coordinates": rounded(g["coordinates"])}
