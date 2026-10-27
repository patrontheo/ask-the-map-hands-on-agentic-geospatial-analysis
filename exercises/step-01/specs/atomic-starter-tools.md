# Atomic starter tools

The starter supplies discovery, data access and explicit map/UI controls.
Step 1 analytical operations remain unimplemented.

- Replace `load_portfolio`, `load_incident` and `load_districts` with
  `get_dataset(dataset_id, include_geometry=False)`.
- Named datasets are `sites`, `companies`, `districts`, `incident:<id>`, and
  optional `buildings`/`parcels`. `describe_data` lists their IDs and schemas.
- Dataset access returns a table, schema, row count, CRS and a reusable `result_id`.
  It does not show, highlight or zoom anything. Readable coordinates are rounded
  for display only; full precision and geometry stay in backend memory.
- The baseline can request rounded GeoJSON explicitly with `include_geometry=True`.
  Incident processing/source metadata remains visible. Spatial joins and totals
  are never performed by this tool.
- `ToolResult.ok(frame=...)` attaches a private DataFrame/GeoDataFrame excluded
  from API/model JSON. `ctx.get_frame(source)` resolves named datasets or stored
  results and returns a copy, keeping source data and previous results intact.
- Add `show_layer(layer_id)` as the counterpart to `hide_layer`. Neither zooms.
- Highlighting ensures sites are visible but does not move the camera. It accepts
  explicit site IDs or a result containing a `site_id` column; empty input clears.
- `zoom_map` remains a separate camera operation and can use a spatial result.
- Update prompts, exercises and tests for these contracts. Preserve the initial
  overview, source files, reference calculations and frozen answers.

Errors: unknown dataset/result/layer/site IDs return actionable hints; results
without dataset data or suitable site/geometry columns return `invalid_dataset`.

Validation: dataset/reference round trips, session isolation, full geometry and
precision preservation, JSON serialization, explicit map actions, agent orchestration,
existing reference checks and frontend regressions. No new runtime dependencies.
