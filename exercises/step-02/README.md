# Step 2: build and interpret a trace viewer

## Completed trace first

Build a trace viewer attached to each assistant response. Use a clearly labelled **Show trace** control that opens a closable pane.
The backend already returns events and tool results; inspect their contract first.
The target is a working viewer for completed answers that also shows what each
answer cost. Live updates, charts and broad UI redesign are outside the task.

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
Open a trace in your browser and check its timings and cost. If something is wrong
or unavailable, tell your assistant what you see and let it fix it.
If blocked, save progress and ask a facilitator for recovery help.

## Cost tracking

Add an estimated API cost to the trace. Use these prices; do not research others.

`gpt-6-luna`, Standard tier, USD per million tokens, checked 27 October 2026
([published prices](https://developers.openai.com/api/docs/models/gpt-6-luna)):

| Token type          | USD / 1M |
| ------------------- | -------: |
| Input               |     0.10 |
| Cache read          |     0.01 |
| Cache write, 30 min |    0.125 |
| Cache write, 12 h   |     0.25 |
| Output              |     0.50 |

Show the response total, individual model-call costs and API-reported token usage.
Cache reads and writes are part of input tokens, and reasoning tokens are part of
output tokens: do not count them twice. The API reports `cache_write_tokens`
without a lifetime; price them at the 30-minute rate. Missing usage must display
as unavailable, not zero.

## Stretch goal

If you finish early, try one of these optional ideas that practise more GIS:

- Export the affected sites as GeoJSON, open the file in QGIS and compare it with
  the app's map. No coding needed for the comparison.
- Find the sites within 1 km of the burnt area, measuring distance in metres.
- Measure the burnt area of each commune, in hectares.
