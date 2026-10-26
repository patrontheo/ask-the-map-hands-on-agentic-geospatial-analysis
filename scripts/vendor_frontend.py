"""Download the vendored frontend libraries (organiser task; the files are committed). Run: uv run python scripts/vendor_frontend.py"""

import urllib.request
from pathlib import Path

MAPLIBRE_VERSION = "4.7.1"
TARGET = Path(__file__).resolve().parents[1] / "frontend" / "vendor" / "maplibre-gl"
FILES = ["maplibre-gl.js", "maplibre-gl.css"]

TARGET.mkdir(parents=True, exist_ok=True)
for name in FILES:
    url = f"https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/{name}"
    with urllib.request.urlopen(url, timeout=30) as r:
        (TARGET / name).write_bytes(r.read())
    print(f"{name}: {(TARGET / name).stat().st_size:,} bytes")
(TARGET / "VERSION").write_text(f"maplibre-gl {MAPLIBRE_VERSION} (BSD-3-Clause)\n")
