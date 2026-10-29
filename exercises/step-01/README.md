# Step 1: build calculation tools

Build reusable geospatial and tabular tools so the app can answer the three
questions below. Different implementations are expected; the data, screening
rules and correct results remain shared.

The operations below are examples, not a required list. Keep tools reusable
rather than hard-coding an answer for each question. The existing tool and dataset
contracts are described in `AGENTS.md`.

| Operation | Example using the workshop data |
| --- | --- |
| Filter rows | Keep site records for one company in the sites table |
| Spatial match | Match building polygons that intersect the wildfire, including boundary contact |
| Distinct IDs | Keep each affected `site_id` once when several buildings match |
| Aggregate | Sum `tiv_eur` for affected sites, grouped by company |
| Join tables | Match exposed company totals to totals from all company sites |
| Calculate | Divide exposed TIV by full company TIV and multiply by 100 |
| Sort | Rank companies by exposed euros or percentage |
| Intersect and measure | Optional: measure burnt commune area in a projected CRS |

Tool names and decomposition may differ. Check the selected sites and numbers.

## Verify the results

Save your baseline before refreshing. With the supplied `--reload` command, Python
changes normally reload the backend automatically. Wait for startup to finish,
then refresh [the app](http://localhost:8000). Use your chosen port if different.

If the new tools are unavailable or automatic reload fails, press **Ctrl+C** in
the server terminal and run `uv run uvicorn backend.app.main:app --reload --port 8000`
again, then refresh the browser. Configuration changes may also require a restart.

Repeat the same questions:

1. Which sites lie inside the wildfire footprint, and how many distinct sites is that?
2. What TIV do these sites represent, and which companies have the highest exposed TIV?
3. For each company, what share of its full portfolio TIV is inside the footprint?

Compare selections, counts, TIV and rankings with your saved baseline. Explain
which operation supports the change. Company share uses all company sites as the
denominator, including those outside the wildfire. One site contributes its full
TIV once. Building and contents TIV excludes business interruption.

If blocked, save your work and ask a facilitator for checkpoint recovery.

Continue with [Step 2](../step-02/README.md).
