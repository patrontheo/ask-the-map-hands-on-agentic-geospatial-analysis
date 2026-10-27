# Ask the Map: Hands-On Agentic Geospatial Analysis

Workshop repository for the AXA Data Science Summit, Amsterdam, 3 November 2026.

You will build a natural-language spatial analyst that screens a synthetic
insurance portfolio against a real wildfire footprint, build reusable
tools for the agent to compose, and make its execution visible in a trace pane.

## Setup

```bash
uv sync
cp .env.example .env   # then fill in LLM_API_KEY
uv run python scripts/setup_check.py
uv run uvicorn backend.app.main:app --reload
```

Open http://localhost:8000.

The setup check runs offline and never displays credential values. Use `--json` for
a shareable report, then ask a question in the app to check live model access.
The map has a plain background when basemap tiles are blocked. Reloading starts a
fresh chat and map.

The model uses `LLM_REASONING_EFFORT=low` by default for faster workshop answers.
Set it to `medium` in your environment for more reasoning, or to an empty value
to use the deployment default. Lower effort can reduce the manual baseline's
accuracy. Follow-up geometry is loaded only when needed, and independent tools
can run in one model round trip.

The starter has seven tools: `describe_data`, `get_dataset`, `show_layer`,
`hide_layer`, `highlight_sites`, `zoom_map` and `suggest_follow_ups`.
Reading data keeps the map unchanged; displaying a layer or highlighting sites
keeps the camera unchanged. Zooming is an explicit operation.

A site is affected when any of its buildings intersects the wildfire footprint,
even if its map pinpoint is outside. Count each site's full TIV once. Chat shows
the answer and follow-up questions; raw tool results are reserved for the trace pane.

Start with [Step 0](exercises/step-00/README.md), then follow
[Step 1](exercises/step-01/README.md) to build the atomic analysis tools.

Run backend and reference checks with `uv run pytest`. Add acceptance tests for
each new operation as part of Step 1. Frontend regression
checks use Node's built-in runner: `node --test tests/*.test.mjs` (Node 22+;
only needed when developing the frontend).

## Steps

| Step | Stage |
|------|-------|
| 0 (`main`) | Map, chat, tool framework with data access and map controls |
| 1 | Atomic tools built and composed by the agent |
| 2 | [Trace pane](exercises/step-02/README.md) |
| 3 | Generated analysis and charts (stretch) |

`main` is the Step 0 starter. Checkpoint branches for the later steps are not published yet.

Data: event footprints © Copernicus Emergency Management Service (EMS), © 2026 European Union;
communes (ADMIN EXPRESS) and buildings (BD TOPO) © IGN, Licence Ouverte 2.0. The portfolio,
companies and insured values are synthetic. Sources and processing are listed in `data/catalog.json`
and `prep/README.md`.
