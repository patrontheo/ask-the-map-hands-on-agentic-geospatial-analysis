# Starter response latency

The recorded baseline took 58 seconds: 44 seconds in the model call selecting
sites from GeoJSON, and most of the remainder in additional model round trips.

- Default `LLM_REASONING_EFFORT` to `low`, configurable to `medium` or higher.
  An empty value omits the setting for deployments that do not support it.
- Encourage independent data and map calls in one model response.
- Let `suggest_follow_ups` accept an optional Markdown `answer`. After all calls
  in that response succeed, return this answer without another model request.
  Keep calls without `answer` working as before; errors must still reach the model.
- Keep geometry retrieval, the reference calculations and the seven starter tools.
  Do not add computation tools or simplify geometry to improve baseline speed.

Verify request settings without network calls, the final answer with a batch of
map calls, and error recovery before finishing. Run the backend and frontend tests.
Compare live latency and manual-answer quality on the deployment.

One live check with `low` effort took 12.6 seconds and four model calls for the
first footprint question, versus 57.9 seconds and six calls in the supplied trace.
The TIV follow-up took 8.9 seconds and two calls. The first answer selected 21 sites
against the reference 40, so the faster manual baseline remains inaccurate.
