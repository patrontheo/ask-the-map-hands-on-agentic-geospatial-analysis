# Step 2 — see how the agent answered

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
