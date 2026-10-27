"""Incident definitions and footprint loading shared by the prep scripts."""

from pathlib import Path

import geopandas as gpd
import shapely

PREP = Path(__file__).parent
RAW = PREP / "raw"
SOURCES = PREP / "sources"
WORK = PREP / "work"
OUT = PREP / "out"  # organiser-only outputs (answer key)
DATA = PREP.parent / "data"  # the app's data bundle

CRS_PROJECTED = "EPSG:2154"

INCIDENTS = {
    "wildfire_leporge_2026": {
        "peril": "wildfire",
        "event_name": "Le Porge wildfire, Gironde",
        "footprint_date": "2026-07-29",
        "product_id": "EMSR899_AOI01_DEL_MONIT02_v1",
        "zip": "wildfire_leporge_2026/EMSR899_AOI01_DEL_MONIT02_v1.zip",
        "layer": "EMSR899_AOI01_DEL_MONIT02_observedEventA_v1.shp",
        "layer_description": "observed burnt area",
        "attribution": "Copernicus Emergency Management Service (© 2026 European Union), "
        "[EMSR899] Le Porge (AOI01): Delineation Map, Monitoring 2",
    },
}

# Not in the bundle for now; move back into INCIDENTS to reactivate.
PARKED = {
    "flood_garonne_2026": {
        "peril": "flood",
        "event_name": "Garonne flood, Gironde and Lot-et-Garonne",
        "footprint_date": "2026-02-14",
        "product_id": "EMSR866_AOI06_DEL_MONIT01_v3",
        "zip": "flood_garonne_2026/EMSR866_AOI06_DEL_MONIT01_v3.zip",
        "layer": "EMSR866_AOI06_DEL_MONIT01_modelledEventA_v3.shp",
        "layer_description": "observed and modelled flood extent",
        "attribution": "Copernicus Emergency Management Service (© 2026 European Union), "
        "[EMSR866] Bordeaux (AOI06): Delineation Map, Monitoring 1",
    },
}


def read_layer(incident_id: str) -> gpd.GeoDataFrame:
    """The published EMS layer, as delivered. Only build_events.py uses it."""
    inc = INCIDENTS[incident_id]
    return gpd.read_file(f"/vsizip/{RAW / inc['zip']}/{inc['layer']}")


def event_file(incident_id: str):
    return DATA / "events" / f"{incident_id}.geojson"


def footprint_wgs84(incident_id: str):
    """The incident footprint as the app uses it (data/events, written by build_events.py), EPSG:4326."""
    return shapely.union_all(gpd.read_file(event_file(incident_id)).geometry.values)


def footprint_projected(incident_id: str):
    """The incident footprint as the app uses it, in EPSG:2154 for inclusion tests."""
    return shapely.union_all(gpd.read_file(event_file(incident_id)).to_crs(CRS_PROJECTED).geometry.values)
