# Step 2 — see how the agent answered

## 1. Build the trace pane

Build a trace viewer for each assistant response. Add a small icon beside the
response that opens a closable overlay pane showing the execution behind that answer.

The pane should show:

- Model calls and tool calls in execution order, including their status.
- Time spent in each step, plus the total time and a breakdown of model versus tool time.
- Expandable step details: inputs, outputs and errors where available, such as
  tool arguments and result previews.

Keep trace details out of the answer itself. Clicking an older response should
show that response's trace, not the most recent one.

The backend already returns trace events and tool results with each answer.
Showing the completed trace is enough for this exercise; live updates are optional.

Ask the same questions again and inspect their traces. Which tools did the agent
use? How did their outputs contribute to the answer? Where was most of the time spent?

## 2. Add cost tracking

Once the pane works, extend it to show the estimated model API cost:

- The total cost of producing that response at the top of the pane.
- The individual cost of each model call.
- A token breakdown: input, output, and cache reads/writes where reported by the API.

Use the prices for the deployed model, make the pricing assumptions visible, and
label the figures as estimates. Sum all model calls for the response total, avoiding
double-counting cached input or reasoning tokens. Missing usage or unknown prices
should appear as unavailable, not as zero cost.

Re-ask the questions and compare costs. Which calls are most expensive? How much
does caching help? Are the slowest steps also the most expensive?
