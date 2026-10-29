# Step 2: build and interpret a trace viewer

## Completed trace first

Build a trace viewer attached to each assistant response. Use a clearly labelled **Show trace** control that opens a closable pane.
The backend already returns events and tool results; inspect their contract first.
The first target is a working viewer for completed answers. Live updates, charts,
pricing and broad UI redesign are outside the core task.

Show a readable sequence containing:

- The question, model calls, tool calls and final answer, in recorded order.
- Tool names with relevant arguments, status, result summaries and returned tables.
- Available durations, with model and tool time shown separately.
- Errors and missing information. Missing timing is unavailable, not zero.

Keep large JSON payloads in expandable details. Pair a tool call and result using
`call_id`; resolve returned data using `result_id`. Each older answer must open its
own trace. Keep the question visible. A request event contains metadata, not the
complete model input. Do not invent private thoughts or explanations of why the
model chose a tool. Display only recorded information.

Wait for automatic backend reload after Python changes, then refresh the app.
Use the restart fallback in Step 1 if needed. Save answers before refreshing.

## Run and interpret

Repeat the questions:

1. Which sites lie inside the wildfire footprint, and how many distinct sites is that?
2. What TIV do these sites represent, and which companies have the highest exposed TIV?
3. For each company, what share of its full portfolio TIV is inside the footprint?

Open one answer's trace. Identify the operation and returned records that establish
the selection, where distinct sites are counted, and which source supplies the
full-company denominator. Tool names and call order may differ across pairs.
A trace makes execution visible; correct-looking calls still need correct data
and calculations. Compare the answer with the facilitator's reference.

Check close/reopen, an older answer, keyboard access and an empty/error trace.
If blocked, save progress and ask a facilitator for recovery help.

## Optional: cost tracking

Only after the core viewer and evidence checks work, add an estimated model cost.
Use organiser-verified prices for the deployed model, with date, currency and SKU.
Do not spend the timed exercise researching prices independently.

Show the response total, individual model-call costs and API-reported token usage.
Avoid double-counting cached input or reasoning tokens already included in output.
Missing usage or unknown prices must display as unavailable, not zero. Explain any
cache categories used. Cost tracking is outside the mandatory two-hour route.
