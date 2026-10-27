"""Run the footprinter (IGN BD TOPO buildings + cadastral parcels) on every candidate address.

Needs network access to data.geopf.fr and its own environment (the footprinter pins numpy < 2):

    uv run --no-project --python 3.12 --with /path/to/footprinter-core-engine --with tqdm \
        python prep/footprint_candidates.py

(tqdm: the footprinter imports it at load time but only declares it as a dev dependency.)

Certificates are checked against the OS trust store, so a corporate TLS proxy's root certificate is
accepted. FOOTPRINTER_VERIFY_SSL=False turns checking off entirely; use it only as a last resort.
"""

import argparse
import os
import time

import truststore

# Before requests/urllib3 build any TLS context: their bundled CA list lacks corporate proxy roots.
truststore.inject_into_ssl()

import geojson  # noqa: E402
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

import footprinter  # noqa: E402
from footprinter import FootprintingInput  # noqa: E402
from footprinter.local_handlers.france.footprinter_france import LocalFootprinterFrance  # noqa: E402

from incidents import WORK  # noqa: E402

BUILDING_FIELDS = ["building_id", "cleabs", "nature", "usage_1", "usage_2", "nombre_d_etages", "hauteur", "nombre_de_logements", "area_m2"]
PARCEL_FIELDS = ["parcel_id", "idu", "section", "numero", "code_insee", "code_dep", "code_com", "nom_com", "contenance", "area_m2"]


def keep(gdf: gpd.GeoDataFrame, fields: list[str], candidate_id: str) -> gpd.GeoDataFrame:
    cols = [c for c in fields if c in gdf.columns]
    out = gpd.GeoDataFrame(gdf[cols].copy(), geometry=gdf.geometry.values, crs=gdf.crs or "EPSG:4326")
    out.insert(0, "candidate_id", candidate_id)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", default=str(WORK / "candidates.csv"))
    parser.add_argument("--pause", type=float, default=0.2, help="seconds between addresses, to be gentle with IGN")
    args = parser.parse_args()

    footprinter.config.set_config(
        {
            "COMMON": {
                "caching": True,
                "caching_path": str(WORK / ".footprinter-cache"),
                "services_verify_ssl": os.environ.get("FOOTPRINTER_VERIFY_SSL", "True"),
            },
            "API_KEYS": {},
        }
    )
    # The France handler directly: Footprinter() also builds the US handler, which demands US API keys.
    engine = LocalFootprinterFrance()
    candidates = pd.read_csv(args.candidates, dtype=str)

    buildings, parcels, log = [], [], []
    for i, row in enumerate(candidates.itertuples(), start=1):
        entry = {"candidate_id": row.candidate_id, "n_buildings": 0, "n_parcels": 0, "mode": "", "reason": "", "error": ""}
        try:
            result = engine.process_single(
                FootprintingInput(
                    geocode=geojson.Point((float(row.lon), float(row.lat))),
                    country_code="FR",
                    geocode_resolution="ROOFTOP",
                    geocode_confidence=5,
                    emp_attributes={},
                    # Site mode: every building on the parcel, widened to neighbouring parcels the buildings spill onto.
                    mode_override="site",
                    request_id=row.candidate_id,
                )
            )
            entry.update(mode=result.processing_mode, reason=result.processing_mode_reason_key)
            if result.exception is not None:
                entry["error"] = repr(result.exception)
            if len(result.buildings):
                buildings.append(keep(result.buildings, BUILDING_FIELDS, row.candidate_id))
                entry["n_buildings"] = len(result.buildings)
            if len(result.parcels):
                parcels.append(keep(result.parcels, PARCEL_FIELDS, row.candidate_id))
                entry["n_parcels"] = len(result.parcels)
        except Exception as err:  # keep going; one bad address must not stop the batch
            entry["error"] = repr(err)
        log.append(entry)
        if i == 10 and all(e["error"] and not e["n_buildings"] for e in log):
            raise SystemExit(f"the first 10 candidates all failed; first error:\n{log[0]['error']}")
        if i % 25 == 0 or i == len(candidates):
            ok = sum(1 for e in log if e["n_buildings"])
            print(f"{i}/{len(candidates)} processed, {ok} with a building")
        time.sleep(args.pause)

    WORK.mkdir(exist_ok=True)
    pd.DataFrame(log).to_csv(WORK / "footprint_log.csv", index=False)
    for name, frames in (("candidate_buildings", buildings), ("candidate_parcels", parcels)):
        path = WORK / f"{name}.geojson"
        if frames:
            pd.concat(frames, ignore_index=True).to_file(path, driver="GeoJSON")
        print(f"wrote {path} ({sum(len(f) for f in frames)} features)")


if __name__ == "__main__":
    main()
