# Step 1 — build atomic tools

The starter provides data access, map controls, a tool registry, the agent loop
and reference answers. Participants implement the analytical tools in this exercise;
there are no disabled computation tool solutions to switch on.

Build small operations that the agent can compose:

| Operation | Purpose |
|---|---|
| `filter_rows` | Filter any dataset by column values |
| `spatial_join` | Match two spatial datasets using an explicit predicate |
| `distinct_rows` | Remove duplicates by keys such as `site_id` |
| `aggregate` | Count, count distinct or sum, optionally grouped by columns |
| `join_tables` | Match tables using shared keys |
| `calculate` | Derive a column using arithmetic on existing columns |
| `sort_rows` | Order rows, optionally keeping the first N |

1. Use `ctx.get_frame(source)` to resolve a named dataset or a previous `result_id`
   into a copy of its full DataFrame/GeoDataFrame. Return new intermediate data
   with `dataset_result(summary, frame, data)` from `result.py`: the model gets the
   schema, row count and a readable table; full geometry and precision stay in the backend.
2. Use [SPEC_PROMPT.md](SPEC_PROMPT.md) to specify an operation, then review it with
   [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md).
3. Implement it as `fn(args, ctx)` with `ToolArgs` and `@tool`, in a new module such as
   `backend/app/tools/ops_tools.py`, and import it in `backend/app/tools/__init__.py`.
   Add tests for the operation and chaining. `get_dataset` in `data_tools.py` is the example to follow.
4. Call it directly through `POST /api/tools/<name>` before trying it in the chat.
   Use `GET /api/tools` to inspect its description and schema.
5. Run `uv run pytest`, reload the app, and repeat every question in the prompt library.
   Inspect the recorded tool calls to verify the agent's workflow. Longer chains
   will need a higher `MAX_MODEL_CALLS` than the starter's default of eight.

For company exposure shares, the agent should spatially join sites to the incident,
deduplicate sites, sum TIV by company, independently sum the full portfolio by company,
join those tables, calculate percentages and sort. Reuse the spatial join for sites
in a selected commune and the attribute filter for a selected company.

Acceptance:

- Site IDs/counts and exposed TIV rankings match `tests/expected.json`.
- Commune counts, company filtering and portfolio totals match the source tables.
- Company shares use full-portfolio denominators; include zero exposure and handle
  zero denominators explicitly.
- Spatial predicates include boundary points when requested; overlapping footprint
  polygons do not cause site totals to be counted twice.
- Calculations and map controls remain separate; the agent can highlight a final selection.
- The assistant states its measure for "most affected" and explains that exposed
  TIV cannot determine losses without damage information.

The existing `analysis.py` functions are reference calculations for verification.
Keep them and the frozen answers unchanged while building the general operations.
