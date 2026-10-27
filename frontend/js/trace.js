import { escapeHtml } from "./format.js";

const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
const count = new Intl.NumberFormat("en-GB");
const duration = (ms) => ms == null ? "—" : ms < 1000 ? `${number.format(ms)} ms` : `${number.format(ms / 1000)} s`;

// Pair backend events; tool outputs live in response.results, linked by result_id.
export function buildTrace(response) {
  const events = response.trace ?? [];
  const results = new Map((response.results ?? []).map((result) => [result.result_id, result]));
  const calls = new Map();
  const steps = [];
  let model = null;
  let modelCalls = 0;
  let inputTokens = 0;
  let outputTokens = 0;
  for (const event of events) {
    const payload = event.payload ?? {};
    if (event.type === "llm_request") {
      model = { kind: "model", name: `Model call ${++modelCalls}`, status: "incomplete", input: payload };
      steps.push(model);
    } else if (event.type === "llm_response" && model) {
      Object.assign(model, { status: "ok", durationMs: event.duration_ms, output: payload,
        summary: payload.function_calls?.length
          ? `Requested ${payload.function_calls.map((call) => call.name).join(", ")}` : "Produced an answer" });
      inputTokens += payload.usage?.input_tokens ?? 0;
      outputTokens += payload.usage?.output_tokens ?? 0;
      model = null;
    } else if (event.type === "tool_call") {
      const step = { kind: "tool", name: payload.tool, status: "incomplete", input: payload.args };
      calls.set(payload.call_id, step);
      steps.push(step);
    } else if (event.type === "tool_result") {
      const step = calls.get(payload.call_id);
      if (step) Object.assign(step, { status: payload.status, durationMs: event.duration_ms,
        summary: payload.summary, output: results.get(payload.result_id) ?? payload });
    } else if (event.type === "error") {
      if (payload.where === "model" && model) {
        Object.assign(model, { status: "error", durationMs: event.duration_ms,
          summary: payload.message, output: payload });
        model = null;
      } else {
        steps.push({ kind: "error", name: "Agent stopped", status: "error", summary: payload.message,
          durationMs: event.duration_ms, output: payload });
      }
    }
  }
  const modelMs = steps.filter((step) => step.kind === "model").reduce((sum, step) => sum + (step.durationMs ?? 0), 0);
  const toolMs = steps.filter((step) => step.kind === "tool").reduce((sum, step) => sum + (step.durationMs ?? 0), 0);
  const elapsed = Date.parse(events.at(-1)?.ts) - Date.parse(events[0]?.ts);
  return { steps, modelCalls, toolCalls: calls.size, inputTokens, outputTokens, modelMs, toolMs,
    totalMs: Number.isFinite(elapsed) ? Math.max(0, elapsed) : modelMs + toolMs,
    errors: steps.filter((step) => step.status === "error").length };
}

function jsonPreview(value) {
  if (value == null) return "Not recorded.";
  const text = JSON.stringify(value, null, 2);
  return text.length > 8000 ? `${text.slice(0, 8000)}\n… preview truncated` : text;
}

function outputPreview(output) {
  if (!output?.table) return output;
  return { ...output, table: { ...output.table, rows: output.table.rows.slice(0, 10) } };
}

function stepHtml(step, index) {
  const status = { ok: "OK", error: "Error", incomplete: "Incomplete" }[step.status] ?? step.status;
  const rowCount = step.output?.table?.total_rows;
  const rowsNote = rowCount > 10 ? `<p class="trace-note">Showing the first 10 of ${count.format(rowCount)} table rows.</p>` : "";
  return `<li><details class="trace-step ${step.kind} ${step.status}"${step.status === "error" ? " open" : ""}>
    <summary>
      <span class="trace-step-number">${index + 1}</span>
      <span class="trace-step-label"><strong>${escapeHtml(step.name)}</strong>
        <small>${escapeHtml(step.summary ?? "No completion recorded")}</small></span>
      <span class="trace-status">${escapeHtml(status)}</span>
      <span class="trace-duration">${duration(step.durationMs)}</span>
      <span class="trace-chevron" aria-hidden="true">›</span>
    </summary>
    <div class="trace-step-details">
      <h3>${step.kind === "model" ? "Request metadata" : "Input"}</h3>
      <pre>${escapeHtml(jsonPreview(step.input))}</pre>
      <h3>Output preview</h3>
      <pre>${escapeHtml(jsonPreview(outputPreview(step.output)))}</pre>${rowsNote}
    </div>
  </details></li>`;
}

function traceHtml(message, response) {
  const trace = buildTrace(response);
  const context = `<p class="trace-question">${escapeHtml(message)}</p>`;
  if (!trace.steps.length) return `${context}<p class="trace-empty">No execution steps were recorded for this response.</p>`;
  const timedMs = trace.modelMs + trace.toolMs;
  const modelPercent = timedMs > 0 ? 100 * trace.modelMs / timedMs : 0;
  const tokens = trace.inputTokens || trace.outputTokens
    ? ` · ${count.format(trace.inputTokens)} input / ${count.format(trace.outputTokens)} output tokens` : "";
  return `${context}
    <div class="trace-stats">
      <div><span>Total agent time</span><strong>${duration(trace.totalMs)}</strong></div>
      <div><span>Model</span><strong>${duration(trace.modelMs)}</strong></div>
      <div><span>Tools</span><strong>${duration(trace.toolMs)}</strong></div>
    </div>
    <div class="trace-timebar" role="img" aria-label="Model time ${duration(trace.modelMs)}, tool time ${duration(trace.toolMs)}">
      <span class="trace-model-time" style="width:${modelPercent}%"></span>
      <span class="trace-tool-time" style="width:${timedMs > 0 ? 100 - modelPercent : 0}%"></span>
    </div>
    <p class="trace-counts">${trace.modelCalls} model call(s) · ${trace.toolCalls} tool call(s)${tokens}
      ${trace.errors ? ` · <span class="trace-errors">${trace.errors} failed step(s)</span>` : ""}</p>
    <ol class="trace-steps">${trace.steps.map(stepHtml).join("")}</ol>
    <p class="trace-note">Recorded agent execution; excludes browser request time and map rendering.
      Model inputs show recorded request metadata. Long outputs are previewed.</p>`;
}

export function createTraceButton(message, response) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "trace-button";
  button.title = "View execution trace";
  button.setAttribute("aria-label", "View execution trace");
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-controls", "trace-dialog");
  button.innerHTML = `<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" fill="none"
    stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="5" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="12" r="2"/>
    <path d="M5 7v10M7 5h3a4 4 0 0 1 4 4v0a3 3 0 0 0 3 3M7 19h3a4 4 0 0 0 4-4v0a3 3 0 0 1 3-3"/>
  </svg>`;
  // Each button closes over its own response, including when older messages are reopened.
  button.addEventListener("click", () => {
    const content = document.getElementById("trace-content");
    content.innerHTML = traceHtml(message, response);
    content.scrollTop = 0;
    const dialog = document.getElementById("trace-dialog");
    if (!dialog.open) dialog.showModal();
  });
  return button;
}

export function initTrace() {
  const dialog = document.getElementById("trace-dialog");
  document.getElementById("trace-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) {
      dialog.close();
    }
  });
  // Native dialog handles Escape, focus trapping and returning focus to the trace button.
}
