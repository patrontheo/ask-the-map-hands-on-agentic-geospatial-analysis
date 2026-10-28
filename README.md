# Ask the Map

Workshop repository for the AXA Data Science Summit, Amsterdam, 4 November 2026.

Build an AI assistant that answers geospatial questions about a synthetic
insurance portfolio and a real wildfire footprint.

This checkpoint includes the calculation tools, trace pane and API cost estimates.

## Setup

Clone the starter branch, then install the dependencies:

```bash
git clone --depth 1 --single-branch --branch main \
  https://github.com/patrontheo/ask-the-map-hands-on-agentic-geospatial-analysis.git ask-the-map-workshop
cd ask-the-map-workshop
uv sync
cp .example.env .env
```

Fill in `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` in `.env` using the values
provided by the organisers. Then check your setup and start the app:

```bash
uv run python scripts/setup_check.py
uv run uvicorn backend.app.main:app --reload --port 8000
```

Open [localhost:8000](http://localhost:8000). If that port is busy, change
`--port 8000` and open the corresponding URL.

The setup check verifies your local environment, settings, data and backend.
It makes no model requests; ask a question in the app to check API access.

## Coding assistant

Follow the [coding assistant setup](coding-assistant/README.md) to use
Codex CLI (Luna) or Claude Code (Haiku) with the workshop endpoints and the
same `.env` file. No personal subscription is required.

## Exercises


| Step                | Exercise                                                          |
| ------------------- | ----------------------------------------------------------------- |
| 0 (`main`)          | [Try the baseline](exercises/step-00/README.md)                   |
| 1 (`step-01-tools`) | [Build calculation tools](exercises/step-01/README.md)            |
| 2 (`step-02-trace`) | [Add a trace pane and cost tracking](exercises/step-02/README.md) |
| 3                   | Generated analysis and charts (stretch)                           |




## Data

Event footprints © Copernicus Emergency Management Service (EMS), © 2026 European Union;
communes (ADMIN EXPRESS) and buildings (BD TOPO) © IGN, Licence Ouverte 2.0. The portfolio,
companies and insured values are synthetic. See [data sources](data/catalog.json)
and [data preparation](prep/README.md).
