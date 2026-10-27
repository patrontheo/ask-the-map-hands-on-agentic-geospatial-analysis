import assert from "node:assert/strict";
import test from "node:test";

import { buildTrace, createTraceButton, initTrace } from "../frontend/js/trace.js";

function response() {
  return {
    turn_id: "t_0001",
    results: [{ result_id: "r_0001", tool: "aggregate", status: "ok", summary: "Portfolio total.",
      table: { columns: [{ name: "tiv_eur" }], rows: [{ tiv_eur: 100 }], total_rows: 1 } }],
    trace: [
      { type: "user_message", ts: "2026-10-27T12:00:00.000Z", payload: { text: "Total?" } },
      { type: "llm_request", payload: { model: "test-model", n_items: 1 } },
      { type: "llm_response", duration_ms: 1200, payload: { text: "", usage: { input_tokens: 100, output_tokens: 20 },
        function_calls: [{ call_id: "c1", name: "aggregate" }] } },
      { type: "tool_call", payload: { call_id: "c1", tool: "aggregate", args: { source: "sites" } } },
      { type: "tool_result", duration_ms: 2.5,
        payload: { call_id: "c1", result_id: "r_0001", status: "ok", summary: "Portfolio total." } },
      { type: "llm_request", payload: { model: "test-model", n_items: 4 } },
      { type: "llm_response", duration_ms: 250, payload: { text: "EUR 100.", function_calls: [],
        usage: { input_tokens: 120, output_tokens: 40 } } },
      { type: "assistant_message", ts: "2026-10-27T12:00:01.460Z", payload: { text: "EUR 100." } },
    ],
  };
}

function setupDom(t) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "document");
  t.after(() => {
    if (descriptor) Object.defineProperty(globalThis, "document", descriptor);
    else delete globalThis.document;
  });
  const element = () => ({
    innerHTML: "", listeners: new Map(), attributes: new Map(),
    addEventListener(type, callback) { this.listeners.set(type, callback); },
    setAttribute(name, value) { this.attributes.set(name, value); },
    click() { this.listeners.get("click")?.({ clientX: 30, clientY: 30 }); },
  });
  const elements = new Map(["trace-dialog", "trace-content", "trace-close"].map((id) => [id, element()]));
  const dialog = elements.get("trace-dialog");
  Object.assign(dialog, { open: false, showModal() { this.open = true; }, close() { this.open = false; },
    getBoundingClientRect: () => ({ left: 10, top: 10, right: 100, bottom: 100 }) });
  globalThis.document = { createElement: element, getElementById: (id) => elements.get(id) };
  initTrace();
  return { dialog, content: elements.get("trace-content"), close: elements.get("trace-close") };
}

test("pairs calls with results in execution order and separates model/tool timing", () => {
  const turn = response();
  const trace = buildTrace(turn);
  assert.deepEqual(trace.steps.map((step) => step.name), ["Model call 1", "aggregate", "Model call 2"]);
  assert.equal(trace.steps[1].output, turn.results[0]);
  assert.deepEqual(trace.steps[1].input, { source: "sites" });
  assert.equal(trace.modelMs, 1450);
  assert.equal(trace.toolMs, 2.5);
  assert.equal(trace.totalMs, 1460);
  assert.equal(trace.inputTokens, 220);
  assert.equal(trace.outputTokens, 60);
  assert.equal(trace.modelCalls, 2);
  assert.equal(trace.toolCalls, 1);
  assert.equal(trace.errors, 0);
});

test("records failed model calls and tool errors without losing their timings", () => {
  const turn = response();
  turn.results[0].status = "error";
  turn.results[0].error = { code: "invalid_column", hint: "Use tiv_eur." };
  turn.trace[4].payload.status = "error";
  turn.trace[6] = { type: "error", duration_ms: 50, payload: { where: "model", message: "Request timed out." } };
  const trace = buildTrace(turn);
  assert.equal(trace.errors, 2);
  assert.equal(trace.steps[1].output.error.hint, "Use tiv_eur.");
  assert.equal(trace.steps[2].status, "error");
  assert.equal(trace.steps[2].durationMs, 50);
  assert.equal(trace.modelMs, 1250);
});

test("loop errors and missing traces have a usable representation", (t) => {
  const { content } = setupDom(t);
  const turn = { trace: [{ type: "error", payload: { where: "loop", message: "Too many steps." } }] };
  assert.equal(buildTrace(turn).steps[0].name, "Agent stopped");
  createTraceButton("A question", turn).click();
  assert.match(content.innerHTML, /trace-step error error" open/);
  assert.match(content.innerHTML, /Too many steps/);
  createTraceButton("Empty", { trace: [], results: [] }).click();
  assert.match(content.innerHTML, /No execution steps were recorded/);
});

test("each response button reopens its own trace; close and backdrop dismiss the overlay", (t) => {
  const { dialog, content, close } = setupDom(t);
  const older = createTraceButton("First question", response());
  const newerTurn = response();
  newerTurn.trace[3].payload.tool = "measure_area";
  const newer = createTraceButton("Second question", newerTurn);
  assert.equal(older.attributes.get("aria-haspopup"), "dialog");
  newer.click();
  assert.equal(dialog.open, true);
  assert.match(content.innerHTML, /Second question/);
  assert.match(content.innerHTML, /<strong>measure_area<\/strong>/);
  content.scrollTop = 300;
  close.click();
  assert.equal(dialog.open, false);
  older.click();
  assert.match(content.innerHTML, /First question/);
  assert.match(content.innerHTML, /<strong>aggregate<\/strong>/);
  assert.equal(content.scrollTop, 0);
  assert.doesNotMatch(content.innerHTML, /Second question/);
  dialog.listeners.get("click")({ clientX: 30, clientY: 30 });
  assert.equal(dialog.open, true, "Clicking inside the panel must not close it");
  dialog.listeners.get("click")({ clientX: 200, clientY: 200 });
  assert.equal(dialog.open, false);
});

test("previews are bounded and escaped without mutating the original outputs", (t) => {
  const { content } = setupDom(t);
  const turn = response();
  turn.trace[3].payload.args = { text: "</pre><script>alert(1)</script>" };
  turn.results[0].table.rows = Array.from({ length: 21 }, (_, i) => ({ value: `ROW_${i}` }));
  turn.results[0].table.total_rows = 21;
  createTraceButton("<img src=x onerror=alert(1)>", turn).click();
  assert.doesNotMatch(content.innerHTML, /<script>|<img/);
  assert.match(content.innerHTML, /&lt;script&gt;/);
  assert.match(content.innerHTML, /ROW_0/);
  assert.doesNotMatch(content.innerHTML, /ROW_20/);
  assert.match(content.innerHTML, /first 10 of 21 table rows/);
  assert.equal(turn.results[0].table.rows.length, 21);
  turn.trace[3].payload.args = { text: "a".repeat(9000) + "HIDDEN_TAIL" };
  createTraceButton("Long input", turn).click();
  assert.match(content.innerHTML, /preview truncated/);
  assert.doesNotMatch(content.innerHTML, /HIDDEN_TAIL/);
});
