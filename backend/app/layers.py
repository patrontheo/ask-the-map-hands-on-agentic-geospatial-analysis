"""Map layers the frontend can show. Tools refer to layers by ID; the frontend fetches their GeoJSON."""

import json

import geopandas as gpd

from backend.app.data import Bundle
from backend.app.footprints import FootprintNotPrepared, footprint_geojson, simplified_footprint

SITE_PROPERTIES = ["site_id", "company_id", "company_name", "address", "city", "district_name",
                   "property_type", "tiv_eur"]


class UnknownLayer(KeyError):
    pass


def list_layers(bundle: Bundle) -> list[dict]:
    layers = [{"id": "sites", "name": "Portfolio sites", "kind": "sites"},
              {"id": "districts", "name": "Districts", "kind": "districts"}]
    for i in bundle.incidents.values():
        layers.append({"id": f"incident:{i.id}", "name": i.meta.get("name", i.id), "kind": "incident",
                       "peril": i.meta.get("peril"), "incident_id": i.id})
        layers.append({"id": f"simplified:{i.id}", "name": f"{i.meta.get('name', i.id)} (simplified, as read by the model)",
                       "kind": "simplified_footprint", "incident_id": i.id})
    if bundle.buildings is not None:
        layers.append({"id": "buildings", "name": "Buildings", "kind": "buildings"})
    if bundle.parcels is not None:
        layers.append({"id": "parcels", "name": "Parcels", "kind": "parcels"})
    for layer in layers:
        layer["url"] = f"/api/layers/{layer['id']}"
    return layers


def layer_ids(bundle: Bundle) -> list[str]:
    return [layer["id"] for layer in list_layers(bundle)]


def _incident_id(bundle: Bundle, layer_id: str, prefix: str) -> str | None:
    if layer_id.startswith(prefix) and layer_id[len(prefix):] in bundle.incidents:
        return layer_id[len(prefix):]
    return None


def layer_frame(bundle: Bundle, layer_id: str) -> gpd.GeoDataFrame:
    if layer_id == "sites":
        sites = bundle.sites.join(bundle.companies.company_name, on="company_id")
        return sites[SITE_PROPERTIES + ["geometry"]]
    if layer_id == "districts":
        return bundle.districts[["district_code", "district_name", "geometry"]]
    if incident_id := _incident_id(bundle, layer_id, "incident:"):
        incident = bundle.incidents[incident_id]
        return incident.polygons[["geometry"]].assign(incident_id=incident_id, peril=incident.meta.get("peril"))
    if incident_id := _incident_id(bundle, layer_id, "simplified:"):
        geom, info = simplified_footprint(bundle, incident_id)
        return gpd.GeoDataFrame({"incident_id": [incident_id], "label": [info.label()]}, geometry=[geom],
                                crs="EPSG:4326")
    if layer_id == "buildings" and bundle.buildings is not None:
        return bundle.buildings
    if layer_id == "parcels" and bundle.parcels is not None:
        return bundle.parcels
    raise UnknownLayer(layer_id)


def layer_geojson(bundle: Bundle, layer_id: str) -> dict:
    if incident_id := _incident_id(bundle, layer_id, "simplified:"):
        try:
            geom, info = simplified_footprint(bundle, incident_id)
        except FootprintNotPrepared as e:
            raise UnknownLayer(layer_id) from e
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": footprint_geojson(geom),
                "properties": {"incident_id": incident_id, "label": info.label()}}]}
    return json.loads(layer_frame(bundle, layer_id).to_json(drop_id=True))


def layer_bbox(bundle: Bundle, layer_id: str) -> list[float]:
    if incident_id := _incident_id(bundle, layer_id, "simplified:"):
        layer_id = f"incident:{incident_id}"  # same extent, and needs no simplified copy
    return [float(v) for v in layer_frame(bundle, layer_id).total_bounds]
