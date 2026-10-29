# Step 1: build calculation tools

Build reusable calculation tools so the app can answer the three questions.
Different implementations are expected; the data, screening rules and correct
results remain shared.

## Research, then implement

1. Ask your coding assistant which calculation tools the app needs to answer the
   three example questions. Ask for small, reusable tools that the app's agent can
   chain, not one tool per question, and no code yet.
2. Review its plan and find at least one thing to correct or make more precise.
   Check the CRS and units, buildings rather than location pins, boundary contact,
   each site counted once, and the full-portfolio denominator. The screening rules
   and the tool contracts are in `AGENTS.md`.
3. Ask it to implement the tools.

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

Compare selections, counts, TIV and rankings with your saved baseline. Look at the
map: are the selected buildings inside or touching the perimeter? Company share uses
all company sites as the denominator, including those outside the wildfire. One site
contributes its full TIV once. Building and contents TIV excludes business interruption.

If blocked, save your work and ask a facilitator for checkpoint recovery.

Continue with [Step 2](../step-02/README.md).
