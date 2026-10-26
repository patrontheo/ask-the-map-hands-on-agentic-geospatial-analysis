# Ask the Map — briefing for coding assistants

A workshop app: a map plus chat where an LLM answers spatial screening
questions about a synthetic insurance portfolio by calling deterministic Python
tools. Real flood and wildfire footprints (Copernicus EMS), synthetic sites and
companies.

## Run and test

```bash
uv sync
uv run uvicorn backend.app.main:app --reload
uv run pytest
```

Credentials live in `.env` (copy `.env.example`). Never print, log, or commit them.

## How the app is organised

- `backend/app/analysis.py`: the spatial functions. Pure, tested. Do not change their results.
- `backend/app/tools/`: tool wrappers. `data_tools.py` loads data and drives the map; `spatial.py` wraps the computations in `analysis.py`. Every tool returns a `ToolResult` built with the helpers in `result.py`; declare tools with `@tool` in `registry.py` (`registered=False` hides a tool from the model). The description and argument schema are what the model sees.
- Tools never send geometry to the map; they return map actions (`show_layer`, `highlight_sites`, `fit_bounds`, …) and the frontend fetches layers from `/api/layers/{id}`.
- `backend/app/agent/`: the Responses API client and the bounded tool loop. It emits trace events; the model never produces tool results.
- `frontend/`: vanilla JS ES modules served by FastAPI. No build step. No new dependencies unless vendored into `frontend/vendor/`.
- `data/`: static data bundle, loaded through `data/catalog.json`. Never hard-code paths or refetch data.

## Geo and screening rules

- Storage and map display in EPSG:4326. Distances and inclusion tests in the projected CRS given per incident in `catalog.json` (metres).
- A site is in a footprint if the footprint `covers` its address point (boundary counts as inside). Union the footprint polygons of an incident first, so each site counts once.
- Exposed TIV = sum of `tiv_eur` (building + contents, EUR, no BI) over distinct sites in the footprint. It is a screening measure: never call it loss, damage, or payout.
- Company exposure share uses the company's full portfolio TIV as the denominator.

## Rules

- Do not edit `tests/expected.json` or existing acceptance tests to make them pass. Add new tests next to them.
- Keep changes small and readable; participants must be able to explain them.
- Write a short spec before larger changes (see `exercises/step-01/SPEC_PROMPT.md`).
