"""Download IGN BD TOPO buildings and ADMIN EXPRESS communes around each incident footprint.

Needs network access to data.geopf.fr. Writes sources/buildings-<incident>.gpkg and
sources/communes.gpkg. Safe to rerun: tiles already downloaded are kept in sources/tiles/.

Run: uv run python prep/fetch_ign.py
"""

import json
import http.client
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import geopandas as gpd
import pandas as pd
import shapely

from incidents import CRS_PROJECTED, INCIDENTS, SOURCES, footprint_projected

try:  # use the OS trust store, so corporate TLS proxies work
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

WFS = "https://data.geopf.fr/wfs/ows"
BUILDING_LAYER = "BDTOPO_V3:batiment"
REGION_M = 6_000  # buildings and communes up to this distance from the footprint
TILE_M = 5_000
PAGE = 5_000
USAGES = {
    "flood_garonne_2026": ["Industriel", "Commercial et services", "Agricole"],
    "wildfire_leporge_2026": ["Industriel", "Commercial et services", "Agricole", "Indifférencié"],
}
BUILDING_FIELDS = ["cleabs", "nature", "usage_1", "usage_2", "etat_de_l_objet", "nombre_d_etages", "hauteur"]


RETRIES = 6


def get(params: dict, parse=lambda body: body):
    """GET the WFS and parse the body; retry transient failures, including cut-off and garbled responses."""
    url = f"{WFS}?{urllib.parse.urlencode(params)}"
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                return parse(response.read())
        except urllib.error.HTTPError as err:
            if err.code not in (429, 500, 502, 503, 504) or attempt == RETRIES - 1:
                raise RuntimeError(f"HTTP {err.code} for {url}\n{err.read()[:500]!r}") from err
            reason = f"HTTP {err.code}"
        except (OSError, http.client.HTTPException, ValueError, ET.ParseError) as err:
            # OSError: connection reset/refused, timeouts; HTTPException: IncompleteRead; ValueError: truncated JSON.
            if attempt == RETRIES - 1:
                raise RuntimeError(f"{type(err).__name__}: {err} for {url}") from err
            reason = type(err).__name__
        wait = 5 * 2**attempt
        print(f"  {reason}, retrying in {wait} s ({attempt + 1}/{RETRIES - 1})")
        time.sleep(wait)
    raise AssertionError("unreachable")


def layer_names() -> list[str]:
    root = get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetCapabilities"}, ET.fromstring)
    return [el.text for el in root.iter("{http://www.opengis.net/wfs/2.0}Name") if el.text]


def commune_layer(names: list[str]) -> str:
    preferred = [n for n in names if re.fullmatch(r"ADMINEXPRESS-COG(-CARTO)?\.LATEST:commune", n)]
    fallback = sorted(n for n in names if re.search(r"ADMINEXPRESS.*:commune$", n))
    if not preferred + fallback:
        raise RuntimeError("no ADMIN EXPRESS commune layer in the WFS capabilities")
    return (preferred + fallback)[0]


def geometry_name(layer: str) -> str:
    xsd = get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "DescribeFeatureType", "typeNames": layer}, ET.fromstring)
    for el in xsd.iter("{http://www.w3.org/2001/XMLSchema}element"):
        if el.get("type", "").startswith("gml:"):
            return el.get("name")
    return "geometrie"


def fetch_box(layer: str, geom: str, box, extra_cql: str = "") -> gpd.GeoDataFrame:
    xmin, ymin, xmax, ymax = box
    cql = f"BBOX({geom},{xmin},{ymin},{xmax},{ymax},'EPSG:2154')" + (f" AND {extra_cql}" if extra_cql else "")
    features, start, matched = [], 0, None
    while True:
        payload = get({
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "typeNames": layer,
            "outputFormat": "application/json", "srsName": "EPSG:2154",
            "count": PAGE, "startIndex": start, "CQL_FILTER": cql,
        }, json.loads)
        page = payload.get("features", [])
        features += page
        matched = payload.get("numberMatched", matched)
        start += len(page)
        # Page on the server's total when it reports one: it may cap pages below PAGE.
        if not page or (isinstance(matched, int) and start >= matched) or (not isinstance(matched, int) and len(page) < PAGE):
            break
    if not features:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=4326)
    try:
        return interpret(features, box, layer, payload.get("crs"))
    except RuntimeError:
        (SOURCES / "debug-failed-tile.json").write_text(json.dumps({"box": box, "cql": cql, "features": features}))
        raise


def interpret(features: list, box, layer: str, crs_member) -> gpd.GeoDataFrame:
    """Find the coordinate reading (Lambert-93, lon/lat or lat/lon) under which the features lie in the box."""
    raw = gpd.GeoDataFrame.from_features(features)
    n_null = int((raw.geometry.isna() | raw.geometry.is_empty).sum())
    raw = raw[raw.geometry.notna() & ~raw.geometry.is_empty].copy()
    raw["geometry"] = shapely.force_2d(raw.geometry.values)
    # IGN evaluates the BBOX in its own lat/lon storage, so it also returns buildings up to ~200 m past
    # the Lambert-93 box. A coordinate mix-up would be off by tens of km, so 1 km of slack is still a tight check.
    target = shapely.box(*box).buffer(1_000)
    tried = []
    for crs, swap in [("EPSG:2154", False), ("EPSG:4326", False), ("EPSG:4326", True)]:
        geoms = shapely.transform(raw.geometry.values, lambda c: c[:, ::-1]) if swap else raw.geometry.values
        gdf = gpd.GeoDataFrame(raw.drop(columns="geometry"), geometry=geoms, crs=crs)
        try:
            envelopes = gdf.to_crs(CRS_PROJECTED).geometry.envelope
            share = float(envelopes.intersects(target).mean())
        except Exception as err:
            tried.append(f"{crs}{' swapped' if swap else ''}: {type(err).__name__}: {err}")
            continue
        tried.append(f"{crs}{' swapped' if swap else ''}: {share:.1%} in box")
        if share >= 0.9:
            return gdf.to_crs(4326)
    first = shapely.get_coordinates(raw.geometry.values[0])[0].tolist() if len(raw) else None
    raise RuntimeError(
        f"{layer}: no coordinate reading puts the features in the requested box.\n"
        f"  requested box (EPSG:2154): {box}\n  response crs member: {crs_member}\n"
        f"  features: {len(raw)} with geometry, {n_null} null or empty\n"
        f"  first coordinate: {first}\n  bounds of response: {raw.total_bounds.round(4).tolist() if len(raw) else None}\n"
        f"  readings tried: {tried}\n  raw response saved to {SOURCES / 'debug-failed-tile.json'}"
    )


def tiles_for(region) -> list[tuple]:
    xmin, ymin, xmax, ymax = region.bounds
    boxes = []
    x = xmin
    while x < xmax:
        y = ymin
        while y < ymax:
            box = (x, y, min(x + TILE_M, xmax), min(y + TILE_M, ymax))
            if region.intersects(shapely.box(*box)):
                boxes.append(tuple(round(v) for v in box))
            y += TILE_M
        x += TILE_M
    return boxes


def main() -> None:
    SOURCES.joinpath("tiles").mkdir(parents=True, exist_ok=True)
    names = layer_names()
    if BUILDING_LAYER not in names:
        raise RuntimeError(f"{BUILDING_LAYER} not offered; similar: {[n for n in names if 'batiment' in n.lower()][:10]}")
    communes_layer = commune_layer(names)
    building_geom, commune_geom = geometry_name(BUILDING_LAYER), geometry_name(communes_layer)
    print(f"layers: {BUILDING_LAYER} ({building_geom}), {communes_layer} ({commune_geom})")

    regions = []
    for incident_id in INCIDENTS:
        region = footprint_projected(incident_id).simplify(50).buffer(REGION_M)
        regions.append(region)
        usage_cql = "usage_1 IN (" + ",".join(f"'{u}'" for u in USAGES[incident_id]) + ")"
        boxes = tiles_for(region)
        frames = []
        for i, box in enumerate(boxes, start=1):
            cache = SOURCES / "tiles" / f"{incident_id}_{box[0]}_{box[1]}.geojson"
            if not cache.exists():
                tile = fetch_box(BUILDING_LAYER, building_geom, box, usage_cql)
                tile = tile[[c for c in BUILDING_FIELDS if c in tile.columns] + ["geometry"]]
                cache.write_text(tile.to_json() if len(tile) else '{"type": "FeatureCollection", "features": []}')
            features = json.loads(cache.read_text())["features"]
            if features:
                frames.append(gpd.GeoDataFrame.from_features(features, crs=4326))
            if i % 20 == 0 or i == len(boxes):
                print(f"{incident_id}: {i}/{len(boxes)} tiles, {sum(len(f) for f in frames):,} buildings")
        if not frames:
            raise RuntimeError(f"{incident_id}: no buildings returned; check the usage filter {usage_cql}")
        buildings = pd.concat(frames, ignore_index=True).drop_duplicates("cleabs")
        gpd.GeoDataFrame(buildings, geometry="geometry", crs=4326).to_file(SOURCES / f"buildings-{incident_id}.gpkg", driver="GPKG")
        print(f"wrote buildings-{incident_id}.gpkg: {len(buildings):,} buildings, by use {buildings.usage_1.value_counts().to_dict()}")

    frames = [fetch_box(communes_layer, commune_geom, region.bounds) for region in regions]
    communes = pd.concat(frames, ignore_index=True)
    code_col = next(c for c in ("insee_com", "code_insee", "code") if c in communes.columns)
    name_col = next(c for c in ("nom", "nom_officiel", "nom_m") if c in communes.columns)
    communes = communes.rename(columns={code_col: "district_code", name_col: "district_name"})
    communes = communes[["district_code", "district_name", "geometry"]].drop_duplicates("district_code")
    gpd.GeoDataFrame(communes, geometry="geometry", crs=4326).to_file(SOURCES / "communes.gpkg", driver="GPKG")
    print(f"wrote communes.gpkg: {len(communes)} communes")


if __name__ == "__main__":
    main()
