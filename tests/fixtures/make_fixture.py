"""Generate the tiny test bundle in tests/fixtures/bundle/. Run: uv run python tests/fixtures/make_fixture.py"""

import csv
import json
from pathlib import Path

from pyproj import Transformer

OUT = Path(__file__).parent / "bundle"
CRS = "EPSG:2154"
to_ll = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def ll(x, y):
    return list(to_ll.transform(x, y))


def square(x0, y0, x1, y1):
    return [[ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1), ll(x0, y0)]]


def feature_collection(features):
    return {"type": "FeatureCollection", "features": features}


def polygon_feature(props, rings):
    return {"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": rings}}


flood_a = square(700000, 7058000, 702000, 7060000)
flood_b = square(701500, 7058500, 703500, 7060500)
wildfire = square(710000, 7058000, 712000, 7060000)

# (site_id, company_id, x, y, property_type, building, contents, district)
SITES = [
    ("S01", "C01", 701000, 7059000, "office", 3_500_000, 1_500_000, "D1"),
    ("S02", "C01", 701800, 7059500, "warehouse", 2_000_000, 1_000_000, "D1"),  # overlap of A and B
    ("S03", "C01", 704500, 7059000, "office", 1_400_000, 600_000, "D1"),
    ("S04", "C02", None, None, "retail", 700_000, 300_000, "D1"),  # on vertex of flood A
    ("S05", "C02", 703000, 7060000, "hotel", 0, 0, "D1"),  # zero TIV, inside B
    ("S06", "C02", 699500, 7059000, "industrial", 3_000_000, 1_000_000, "D1"),
    ("S07", "C03", 702500, 7059000, "industrial", 3_000_000, 1_000_000, "D1"),
    ("S08", "C03", 711000, 7059000, "warehouse", 4_500_000, 1_500_000, "D2"),
    ("S09", "C03", 706000, 7059000, "office", 700_000, 300_000, "D2"),
    ("S10", "C04", 704000, 7061000, "office", 6_000_000, 2_000_000, "D1"),
    ("S11", "C04", 711500, 7058500, "retail", 1_500_000, 500_000, "D2"),
    ("S12", "C04", 701200, 7058200, "office", 700_000, 300_000, "D1"),
    ("S13", "C01", 704800, 7060500, "industrial", 16_000_000, 6_000_000, "D1"),
]
COMPANIES = [("C01", "Alder Logistics", "logistics"), ("C02", "Birch Hospitality", "hospitality"),
             ("C03", "Cedar Manufacturing", "manufacturing"), ("C04", "Dune Offices", "real estate")]
DISTRICTS = [("D1", "West District", 699000, 7056000, 705000, 7062000),
             ("D2", "East District", 705000, 7056000, 713000, 7062000)]


def main():
    for sub in ("portfolio", "events", "admin"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    write_json(OUT / "events/flood_test.geojson", feature_collection([
        polygon_feature({"incident_id": "flood_test", "part": "A"}, flood_a),
        polygon_feature({"incident_id": "flood_test", "part": "B"}, flood_b),
    ]))
    write_json(OUT / "events/wildfire_test.geojson", feature_collection([
        polygon_feature({"incident_id": "wildfire_test", "part": "A"}, wildfire),
    ]))
    write_json(OUT / "admin/districts.geojson", feature_collection([
        polygon_feature({"district_code": c, "district_name": n}, square(x0, y0, x1, y1))
        for c, n, x0, y0, x1, y1 in DISTRICTS
    ]))

    with open(OUT / "portfolio/sites.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "company_id", "address", "postcode", "city", "district_code", "district_name",
                    "property_type", "lon", "lat", "x", "y", "tiv_building_eur", "tiv_contents_eur", "tiv_eur",
                    "building_id", "parcel_id"])
        names = dict((c, n) for c, n, *_ in DISTRICTS)
        for sid, cid, x, y, ptype, bld, cnt, dist in SITES:
            lon, lat = flood_a[0][0] if x is None else ll(x, y)
            px, py = (700000, 7058000) if x is None else (x, y)
            w.writerow([sid, cid, f"{int(sid[1:])} Test Street", "59000", "Testville", dist, names[dist], ptype,
                        repr(lon), repr(lat), px, py, bld, cnt, bld + cnt, f"B{sid[1:]}", f"P{sid[1:]}"])

    with open(OUT / "portfolio/companies.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company_id", "company_name", "sector"])
        w.writerows(COMPANIES)

    write_json(OUT / "catalog.json", {
        "crs_projected": CRS,
        "currency": "EUR",
        "incidents": [
            {"id": "flood_test", "peril": "flood", "name": "Test flood", "date": "2024-01-01",
             "path": "events/flood_test.geojson", "source": "fixture", "licence": "test"},
            {"id": "wildfire_test", "peril": "wildfire", "name": "Test wildfire", "date": "2024-07-01",
             "path": "events/wildfire_test.geojson", "source": "fixture", "licence": "test"},
        ],
        "portfolio": {"sites": "portfolio/sites.csv", "companies": "portfolio/companies.csv"},
        "districts": "admin/districts.geojson",
    })


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=1) + "\n")


if __name__ == "__main__":
    main()
