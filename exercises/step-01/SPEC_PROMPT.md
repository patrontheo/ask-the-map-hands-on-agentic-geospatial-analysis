# Write a tool spec

Replace `<TOOL_NAME>` and paste this into your coding assistant:

```text
I want to implement the reusable atomic operation `<TOOL_NAME>` for the agent.
Read AGENTS.md, backend/app/tools/{registry,result,data_tools,map_tools}.py, backend/app/datasets.py,
backend/app/analysis.py and data/catalog.json first.

Before changing code, write exercises/step-01/specs/<TOOL_NAME>.md with:
1. Purpose and two example user questions.
2. Arguments, types, defaults and validation. Inherit from ToolArgs. Explain
   how the tool consumes named datasets or previous result_id values with ctx.get_frame.
3. The exact tool description the model will see (up to three lines).
4. The single operation it performs, including CRS and units where applicable.
   Spatial joins must define predicates and treatment of boundary points.
5. ToolResult summary, schema, row count and reusable intermediate data via frame=.
   Keep calculations separate from map display.
6. Errors with hints; empty selections and duplicate IDs.
7. Acceptance tests and reference answers to check.
8. Open questions.

Do not implement yet. Stop after writing the spec.
```

Review it with [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md), then ask the assistant
to implement the approved spec and add its tests. Keep the reference calculations
and frozen answers unchanged.
