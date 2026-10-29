# Step 1: build calculation tools

Use your coding assistant in this starter checkout to give the app agent reusable
geospatial and tabular computation tools. Different implementations are expected.
The same data and screening rules should produce the same selected sites and totals.

## Plan before implementation

Give your coding assistant the business questions below and ask it to propose a
short plan. Review how it selects buildings, keeps distinct site IDs, sums insured
values and constructs each company's full-portfolio denominator. Then ask it to
implement the plan. Work from the current files; do not copy checkpoint solutions.

Build the minimum calculation path first. Keep functions reusable rather than
hard-coding a separate answer for each question. You do not need every operation
listed below. Read `AGENTS.md` for the existing tool and dataset contracts.

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

Names and tool decomposition are choices. Review the selection and returned data,
not whether your assistant copied these names. While code runs, inspect its plan,
identify a building-boundary case, and work out which records belong in a company
denominator. Ask for help if progress stalls; avoid starting a broad rewrite.

## Restart and verify

Save your baseline first. In the terminal running the server, press **Ctrl+C**,
then run `uv run uvicorn backend.app.main:app --reload --port 8000` again. Wait for
startup to finish and refresh [the app](http://localhost:8000). A browser refresh
alone is not a server restart. Use your chosen port if different.

Repeat the same questions:

1. Which sites lie inside the wildfire footprint, and how many distinct sites is that?
2. What TIV do these sites represent, and which companies have the highest exposed TIV?
3. For each company, what share of its full portfolio TIV is inside the footprint?

Compare selections, counts, TIV and rankings with your saved baseline. Explain
which operation supports the change. Company share uses all company sites as the
denominator, including those outside the wildfire. One site contributes its full
TIV once. Building and contents TIV excludes business interruption.

At the facilitator's checkpoint, stop and save progress. If blocked, ask for
assisted checkpoint recovery after preserving your changes. Do not discard work.

Continue with [Step 2](../step-02/README.md).
