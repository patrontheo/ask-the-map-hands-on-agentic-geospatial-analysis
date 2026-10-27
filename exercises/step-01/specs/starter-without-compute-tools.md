# Starter without computation tools

The starter tool inventory is subsequently refined by [atomic-starter-tools.md](atomic-starter-tools.md).

Step 1 is an implementation exercise: participants build reusable atomic operations
and let the agent compose them to answer the prompt library.

- Remove the three specialised tool wrappers and their import from the starter.
  Do not implement their generic replacements or ship disabled solutions.
- Keep the eight data/map/UI tools, dispatcher, result contract and agent loop.
- Preserve `analysis.py` and the frozen answers as reference calculations for
  verification; their selection, aggregation and distance functions are not tools.
- Test the dispatcher and loop with the existing starter tools. Verify that the
  removed names are unavailable even through the direct endpoint.
- Replace registration-only exercise tests with independent reference checks.
  New tool acceptance tests belong with the participant's agreed operation specs.
- Update participant instructions and the model spike to use the starter tools.
  Cover all prompt-library questions through composable operations in Step 1.

Validation: backend suite, independent frozen-reference checks, frontend regressions,
and an inventory confirming that only the eight starter tools are implemented.
