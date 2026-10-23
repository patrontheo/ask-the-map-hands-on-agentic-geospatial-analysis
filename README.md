# Ask the Map: Hands-On Agentic Geospatial Analysis

Workshop repository for the AXA Data Science Summit, Amsterdam, 3 November 2026.

You will build a natural-language spatial analyst that screens a synthetic
insurance portfolio against real flood and wildfire footprints, connect it to
fixed spatial tools, and make its execution visible in a trace pane.

> Work in progress: the app, data and exercises are being built.

## Setup

```bash
uv sync
cp .env.example .env   # then fill in LLM_API_KEY
uv run python scripts/setup_check.py
uv run uvicorn backend.app.main:app --reload
```

Open http://localhost:8000.

## Checkpoints

| Branch | Stage |
|--------|-------|
| `step-00-starter` (= `main`) | Map, data, LLM-only baseline, agent loop |
| `step-01-tools` | Fixed tools connected |
| `step-02-trace` | Trace pane |
| `step-03-analysis` | Generated analysis and charts (stretch) |

Data: event footprints © Copernicus Emergency Management Service; the portfolio,
companies and insured values are synthetic. See `data/LICENCES.md`.
