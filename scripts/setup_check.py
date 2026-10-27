"""Offline workshop preflight. Run with uv run python scripts/setup_check.py [--json]."""

import argparse
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run_checks() -> list[dict]:
    checks = []

    def record(name, ok, message):
        checks.append({"check": name, "ok": bool(ok), "message": message})

    python_ok = sys.version_info[:2] == (3, 12)
    record("Python", python_ok, "Python 3.12." if python_ok else "Python 3.12 required; run uv sync.")
    missing = []
    for name in ("geopandas", "shapely", "pyproj", "pyogrio", "pandas", "fastapi",
                 "uvicorn", "pydantic", "openai", "dotenv", "httpx"):
        try:
            importlib.import_module(name)
        except (ImportError, OSError):
            missing.append(name)
    record("Dependencies", not missing,
           f"Run uv sync; unavailable: {', '.join(missing)}." if missing else "Project imports work.")
    if missing:
        return checks

    from backend.app import config
    from backend.app.data import FIXTURE_DIR, data_dir, get_bundle

    required = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
    unset = [name for name in required if not getattr(config, name).strip()]
    record("Model configuration", not unset,
           f"Set {', '.join(unset)} in .env." if unset else "Required settings are present; values are not displayed.")

    try:
        bundle = get_bundle()
    except Exception as error:
        record("Data", False, f"Bundle could not load ({type(error).__name__}); check DATA_DIR and catalog paths.")
        return checks
    source = "fixture fallback" if data_dir().resolve() == FIXTURE_DIR.resolve() else "workshop bundle"
    record("Data", True, f"Loaded {source}: {len(bundle.sites)} sites, {len(bundle.incidents)} incident(s).")

    from pyproj import Transformer

    point = bundle.sites.geometry.iloc[0]
    projected = bundle.sites_projected.iloc[0]
    inverse = Transformer.from_crs(bundle.crs_projected, "EPSG:4326", always_xy=True)
    lon, lat = inverse.transform(projected.x, projected.y)
    record("Projection", abs(lon - point.x) < 1e-6 and abs(lat - point.y) < 1e-6,
           f"Coordinate round trip through {bundle.crs_projected}; reinstall with uv sync if this fails.")

    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as client:
        response = client.get("/api/tools")
        record("Backend", response.status_code == 200 and bool(response.json()), "In-process /api/tools check.")
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print checks as JSON, without setting values.")
    args = parser.parse_args(argv)
    checks = run_checks()
    if args.json:
        print(json.dumps(checks, indent=2))
    else:
        for check in checks:
            print(f"{'OK' if check['ok'] else 'FAIL'} {check['check']}: {check['message']}")
        print("Offline checks only. Start the app and ask a question to check model access and basemap connectivity.")
    return 0 if all(check["ok"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
