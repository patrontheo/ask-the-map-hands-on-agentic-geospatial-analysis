# Starter fixes

Historical implementation spec. The registration-only Step 1 design below is
superseded by [starter-without-compute-tools.md](starter-without-compute-tools.md).

Purpose: fix the reviewed Step 0 bugs and supply the missing workshop handoff files,
while keeping the deterministic spatial calculations and Step 0 tool registration unchanged.

- Introduce a shared `ToolArgs` model that rejects unknown arguments. All current
  argument models inherit it; malformed calls return `invalid_arguments`.
- Start a new browser session on every page load, matching the fresh transcript and map.
- Share one pending fetch/add operation per map layer. Remove failed pending loads so
  they can be retried. Buildings and parcels use their advertised layer IDs and the
  existing site styles; the portfolio legend controls all three layers together.
- Fade points only for site IDs with visible replacement shapes. Sites without shapes,
  including the fixture fallback, remain visible at every zoom.
- Add an offline setup check for Python, imports, data, projection, configuration and
  the backend. Report missing credentials by variable name only. JSON output is supported;
  no external model or basemap request is needed for this prototype check.
- Add Step 0/1 instructions, the spec prompt, review checklist and Step 1 acceptance
  tests. Keep the computation tools unregistered for the exercise. Mark their expected
  failures explicitly in the starter; they must pass after registration.
- Freeze the current bundle's reference answers from independent point-in-polygon
  checks and raw CSV sums, cross-checked with prep/out/edge_cases.json. Do not derive
  reference answers from the tool implementations or change existing acceptance tests.

Validation: existing pytest suite, new argument/setup regressions, Node's built-in
test runner with mocked map rendering for visibility/concurrency, and Step 1 acceptance
tests with tools registered only in memory. No new runtime dependencies.
