# Ask the Map: Hands-On Agentic Geospatial Analysis

Workshop repository for the AXA Data Science Summit, Amsterdam, 3 November 2026.

You will build a natural-language spatial analyst that screens a synthetic
insurance portfolio against a real wildfire footprint, build reusable
tools for the agent to compose, and make its execution visible in a trace pane.

This branch, `step-02-trace`, contains the calculation tools and the completed Step 2
trace viewer. `main` remains the Step 0 starter; `step-01-tools` contains the calculation tools.

## Setup

```bash
uv sync
cp .example.env .env   # then fill in LLM_BASE_URL, LLM_API_KEY and LLM_MODEL
uv run python scripts/setup_check.py
uv run uvicorn backend.app.main:app --reload
```

Open http://localhost:8000.

Need a coding assistant without a subscription? Follow the
[coding assistant setup](coding-assistant/README.md) to use Codex CLI (Luna) or
Claude Code (Haiku) with the workshop endpoints and the same root `.env` file.
The organisers provide endpoint URLs, deployment names and API keys privately.

The setup check runs offline and never displays credential values. Use `--json` for
a shareable report, then ask a question in the app to check live model access.
The map has a plain background when basemap tiles are blocked. Reloading starts a
fresh chat and map.

The seven data/map/UI tools are `describe_data`, `get_dataset`, `show_layer`,
`hide_layer`, `highlight_sites`, `zoom_map` and `suggest_follow_ups`. This branch adds
`filter_rows`, `spatial_join`, `distinct_rows`, `intersect_geometries`, `measure_area`,
`aggregate`, `join_tables`, `calculate` and `sort_rows`.
Reading data keeps the map unchanged; displaying a layer or highlighting sites
keeps the camera unchanged. Zooming is an explicit operation.

A site is affected when any of its buildings intersects the wildfire footprint,
even if its map pinpoint is outside. Count each site's full TIV once. Chat shows
the answer and follow-up questions. Click the small trace icon beside a response to
inspect its execution without adding raw tool cards to the conversation.

The [Step 0](exercises/step-00/README.md) and [Step 1](exercises/step-01/README.md)
instructions describe the exercises on `main`. On this branch, re-ask the prompt-library
questions to try the implemented tools. The agent can use up to 16 model calls per
turn; set `MAX_MODEL_CALLS` to adjust this for longer workflows.

Run backend and reference checks with `uv run pytest`. Add acceptance tests for
each new operation as part of Step 1. Frontend regression
checks use Node's built-in runner: `node --test tests/*.test.mjs` (Node 22+;
only needed when developing the frontend).

## Steps

| Step | Stage |
|------|-------|
| 0 (`main`) | Map, chat, tool framework with data access and map controls |
| 1 (`step-01-tools`) | [Calculation tools built and composed by the agent](exercises/step-01/README.md) |
| 2 (`step-02-trace`) | [Trace pane and API cost tracking](exercises/step-02/README.md) |
| 3 | Generated analysis and charts (stretch) |

`main` is the Step 0 starter. Checkpoint implementations are available on
`step-01-tools` and `step-02-trace`.

The trace overlay shows ordered model/tool calls, statuses, per-step timings and
total model/tool time. Expand a step for request details, output previews and errors.
Each answer retains its own trace. Traces are available after the answer finishes;
model inputs show recorded request metadata, and long outputs are previewed.

The pane also shows estimated API cost in USD for the whole answer and each model
call. Expand a model call for ordinary input, cache reads, cache writes and output
costs. Reasoning tokens are already included in output. Missing usage is shown as
unavailable, and partial costs are never presented as the total.

Estimates use [GPT-6 Luna Standard public API prices](https://developers.openai.com/api/docs/models/gpt-6-luna),
checked 27 October 2026: $0.10 input, $0.01 cache reads, $0.125 cache writes (30 min)
or $0.25 (12 h), and $0.50 output, per million tokens. Prompts over 272,000 input
tokens use 2× input/cache rates and 1.5× output rates. Cache-write lifetime defaults
to 30 minutes when the API omits it; the trace labels this assumption. This is a
public Standard API equivalent, so provider invoices and regional pricing can differ.
`LLM_PRICING_MODEL` defaults to `gpt-6-luna`, independently of the deployment alias
in `LLM_MODEL`; unsupported pricing models show unavailable until rates are added
in `backend/app/agent/cost.py`.

Data: event footprints © Copernicus Emergency Management Service (EMS), © 2026 European Union;
communes (ADMIN EXPRESS) and buildings (BD TOPO) © IGN, Licence Ouverte 2.0. The portfolio,
companies and insured values are synthetic. Sources and processing are listed in `data/catalog.json`
and `prep/README.md`.
