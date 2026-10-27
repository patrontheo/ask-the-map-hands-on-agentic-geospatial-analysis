# Ask the Map: Hands-On Agentic Geospatial Analysis

Workshop repository for the AXA Data Science Summit, Amsterdam, 3 November 2026.

You will build a natural-language spatial analyst that screens a synthetic
insurance portfolio against real flood and wildfire footprints, build reusable
tools for the agent to compose, and make its execution visible in a trace pane.

> Work in progress: the app, data and exercises are being built.

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

The starter has seven tools: `describe_data`, `get_dataset`, `show_layer`,
`hide_layer`, `highlight_sites`, `zoom_map` and `suggest_follow_ups`.
Reading data keeps the map unchanged; displaying a layer or highlighting sites
keeps the camera unchanged. Zooming is an explicit operation.

Start with [Step 0](exercises/step-00/README.md), then follow
[Step 1](exercises/step-01/README.md) to build the atomic analysis tools.

Run backend and reference checks with `uv run pytest`. Add acceptance tests for
each new operation as part of Step 1. Frontend regression
checks use Node's built-in runner: `node --test tests/frontend.test.mjs` (Node 22+;
only needed when developing the frontend).

## Checkpoints

| Branch | Stage |
|--------|-------|
| `step-00-starter` (= `main`) | Map, chat, tool framework with data access and map controls |
| `step-01-tools` | Atomic tools built and composed by the agent |
| `step-02-trace` | Trace pane |
| `step-03-analysis` | Generated analysis and charts (stretch) |

Data: event footprints © Copernicus Emergency Management Service; the portfolio,
companies and insured values are synthetic. See `data/LICENCES.md`.
