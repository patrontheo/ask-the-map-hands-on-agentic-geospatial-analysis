# Step 1 — give the agent calculation tools

Build tools that let the assistant calculate answers from the portfolio, wildfire
footprint and commune data. Aim for small, reusable operations the agent can combine
to answer different questions.

Example tools:

| Tool | Purpose |
|---|---|
| `filter_rows` | Filter records by attribute values |
| `spatial_join` | Match records based on their spatial relationship |
| `distinct_rows` | Remove duplicate records |
| `intersect_geometries` | Find the overlap between polygons |
| `measure_area` | Measure polygon areas |
| `aggregate` | Count records or sum values, optionally by group |
| `join_tables` | Combine tables using shared keys |
| `calculate` | Calculate new values, such as percentages |
| `sort_rows` | Order or rank results |

These are examples; choose the tools you think the assistant needs.

Reload the app and ask the same questions from Step 0 and the prompt library again.
Compare the figures, rankings, highlighted sites and response times with your
recorded baseline. Which answers changed, and why?

Continue with [Step 2](../step-02/README.md) to make the agent's execution visible.
