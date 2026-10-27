"""Write the incident footprints to data/events/ and the bundle index data/catalog.json.

Each footprint is the published EMS layer generalised to at most MAX_VERTICES (closing small gaps,
dropping small parts, Douglas-Peucker), so the model can read it whole. That generalised shape is
the incident's footprint for everything: tools, map, model and reference answers. Takes several
minutes per incident; every other prep step reads the file written here.

Run: uv run python prep/build_events.py
"""

import json

import geopandas as gpd
import shapely

from generalise import MAX_VERTICES, generalise
from incidents import CRS_PROJECTED, DATA, INCIDENTS, read_layer

LICENCE = ("Copernicus EMS data policy (Regulation (EU) 2021/696): free reproduction, distribution and "
           "adaptation with attribution")


def main() -> None:
    (DATA / "events").mkdir(parents=True, exist_ok=True)
    incidents = []
    for incident_id, inc in INCIDENTS.items():
        full = shapely.make_valid(read_layer(incident_id).to_crs(CRS_PROJECTED).geometry.make_valid().union_all())
        geom, info = generalise(full, MAX_VERTICES)
        processing = (f"Generalised from the published layer to {info.vertices:,} vertices: gaps up to "
                      f"{2 * info.closing_m:g} m closed, parts under {info.min_part_m2 / 1e4:g} ha dropped, "
                      f"{info.tolerance_m:g} m simplification; {info.area_differs_pct:.1f} % of the area differs.")
        wgs84 = gpd.GeoSeries(list(shapely.get_parts(geom)), crs=CRS_PROJECTED).to_crs(4326)
        props = {"incident_id": incident_id, "peril": inc["peril"], "event_name": inc["event_name"],
                 "footprint_date": inc["footprint_date"], "source": inc["attribution"],
                 "product_id": inc["product_id"], "licence": LICENCE}
        features = [{"type": "Feature", "properties": props, "geometry": shapely.geometry.mapping(g)} for g in wgs84]
        rel = f"events/{incident_id}.geojson"
        # json.dumps writes the shortest exact float repr, so coordinates round-trip unchanged.
        (DATA / rel).write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
        incidents.append({"id": incident_id, "peril": inc["peril"], "name": inc["event_name"], "date": inc["footprint_date"],
                          "crs_projected": CRS_PROJECTED, "path": rel, "layer": inc["layer_description"],
                          "processing": processing, "source": inc["attribution"], "product_id": inc["product_id"],
                          "licence": LICENCE})
        print(f"{rel}: {len(features)} polygons, {(DATA / rel).stat().st_size / 1e3:.0f} KB. {processing}")

    catalog = {
        "crs_projected": CRS_PROJECTED,
        "currency": "EUR",
        "incidents": incidents,
        "portfolio": {"sites": "portfolio/sites.csv", "companies": "portfolio/companies.csv",
                      "buildings": "portfolio/buildings.geojson", "parcels": "portfolio/parcels.geojson"},
        "districts": "admin/districts.geojson",
    }
    (DATA / "catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    print("wrote data/catalog.json")


if __name__ == "__main__":
    main()
