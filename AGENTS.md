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

Credentials live in `.env` (copy `.example.env`). Never print, log, or commit them.

## How the app is organised

- `backend/app/analysis.py`: pure reference calculations and helpers used by the data/map tools. They follow the screening rules below; the selection, aggregation and distance functions are not registered tools.
- `backend/app/tools/`: data/map/UI tools live in `data_tools.py`, `map_tools.py` and `chat_tools.py`. Reusable calculations live in `table_tools.py` and `spatial_tools.py`; `main` remains the Step 0 starter. A tool is `fn(args, ctx) -> ToolResult` declared with `@tool` from `registry.py`; the bundle is `ctx.bundle`. Argument models inherit `ToolArgs` to reject unknown fields. The description and argument schema are what the model sees. Import new tool modules in `tools/__init__.py` to register them.
- `backend/app/datasets.py`: resolves named source tables (`sites`, `companies`, `districts`, `incident:<id>`, optional `buildings`/`parcels`). Use `ctx.get_frame(source)` to read a copy of a source or previous dataset result. Return `dataset_result(summary, frame, data)` from `result.py` to make intermediate data reusable: it adds the readable table, schema, row count and CRS, and keeps the frame private (excluded from API/model JSON).
- `get_dataset` reads data without map actions. `show_layer`/`hide_layer` control visibility, `highlight_sites` applies site highlights without zooming, and `zoom_map` moves the camera. Full geometry and precision stay in the backend; `include_geometry=True` supplies rounded GeoJSON for baseline reasoning.
- Tools never send geometry to the map; they return map actions (`show_layer`, `highlight_sites`, `fit_bounds`, …) and the frontend fetches layers from `/api/layers/{id}`.
- `backend/app/agent/`: the Responses API client and the bounded tool loop. It emits trace events; the model never produces tool results.
- `backend/app/agent/cost.py`: public Luna Standard API estimates from the full recorded usage, including cache reads/writes. Pricing is separate from the deployment alias (`LLM_PRICING_MODEL`). Cache usage is part of input and reasoning part of output; never double-count them. Missing usage/rates means unavailable. The trace pane sums per-call estimates only when all calls are priced.
- The loop omits earlier turns' GeoJSON from model input, retaining tables, result IDs and a reload hint. Geometry requested with `get_dataset(include_geometry=True)` stays in context for the current turn; full results and frames remain in the session for later tools.
- Model reasoning defaults to `LLM_REASONING_EFFORT=low`. `suggest_follow_ups(answer=...)` finishes a turn without another model request after all tools in that batch succeed; errors still go back to the model. Independent calls can share a batch, but a result ID is only available after its producing call executes.
- `frontend/`: vanilla JS ES modules served by FastAPI. No build step. No new dependencies unless vendored into `frontend/vendor/`.
- Chat displays the assistant's Markdown answer, follow-up buttons and a trace icon. `frontend/js/trace.js` pairs execution events with tool results and opens a modal for that response. Keep raw tool cards out of the answer. Model inputs show recorded metadata; outputs are bounded previews. The API response and `chat:turn` event still carry the full recorded turn.
- `data/`: static data bundle, loaded through `data/catalog.json`. Never hard-code paths or refetch data.

## Geo and screening rules

- Storage and map display in EPSG:4326. Distances and inclusion tests in the projected CRS given per incident in `catalog.json` (metres).
- A site is affected if any of its buildings `intersects` the footprint, including boundary contact. A pinpoint outside the footprint does not exclude a site. Deduplicate by `site_id` and count its full TIV once. Point coverage is an explicit fallback only for bundles without building geometry.
- Exposed TIV = sum of `tiv_eur` (building + contents, EUR, no BI) over distinct sites in the footprint. It is a screening measure: never call it loss, damage, or payout.
- Company exposure share uses the company's full portfolio TIV as the denominator.

## Rules

- Keep expected answers independent of tool implementations. Regenerate them from source data only when inputs or the screening definition deliberately change; never change expectations to conceal a failing tool.
- Keep changes small and readable; participants must be able to explain them.
- Keep exercise instructions focused on the goal; participants choose how to implement their tools.
