# Review your tool spec

- Does the tool perform one reusable operation that can serve multiple questions?
- Do argument models inherit `ToolArgs` and reject unknown fields?
- Do spatial predicates handle boundary points explicitly, with duplicates removed before site totals?
- Are distances in the projected CRS, money in EUR, and site IDs distinct?
- Does the summary state the count, measure and scope without requiring model arithmetic?
- Are `result_id` chaining, empty selections and duplicate IDs handled?
- Do errors include hints with valid IDs or corrected arguments?
- Does full intermediate data stay in the backend while the model gets its schema and preview?
- Are calculations separate from map display?
- Do tests cover the operation and its composition with the other tools?
- Can the resulting toolkit answer every prompt-library question, including company shares?

Never change `analysis.py`, acceptance expectations or `tests/expected.json` to make
a failing tool pass.
