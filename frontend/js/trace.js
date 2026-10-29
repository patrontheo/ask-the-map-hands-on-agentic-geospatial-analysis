import { escapeHtml } from "./format.js";

const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
const count = new Intl.NumberFormat("en-GB");
const rate = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });
const duration = (ms) => ms == null ? "Unavailable" : ms < 1000 ? `${number.format(ms)} ms` : `${number.format(ms / 1000)} s`;
const dollars = (value) => value == null ? "Unavailable"
  : value > 0 && value < 0.000001 ? "<$0.000001" : `$${value.toFixed(6)}`;
const hasCost = (step) => step.cost?.status === "estimated"
  && Number.isFinite(step.cost.total_usd) && step.cost.total_usd >= 0;

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
      Object.assign(model, { status: "ok", durationMs: event.duration_ms, output: payload, cost: payload.cost,
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
  const modelSteps = steps.filter((step) => step.kind === "model");
  const sumDuration = (items) => items.some((step) => !Number.isFinite(step.durationMs)) ? null : items.reduce((sum, step) => sum + step.durationMs, 0);
  const modelMs = sumDuration(modelSteps);
  const pricedSteps = modelSteps.filter(hasCost);
  const knownCostUsd = pricedSteps.reduce((sum, step) => sum + step.cost.total_usd, 0);
  const unpricedCalls = modelCalls - pricedSteps.length;
  const toolMs = sumDuration(steps.filter((step) => step.kind === "tool"));
  const elapsed = Date.parse(events.at(-1)?.ts) - Date.parse(events[0]?.ts);
  return { steps, modelCalls, toolCalls: calls.size, inputTokens, outputTokens, modelMs, toolMs,
    knownCostUsd, unpricedCalls, totalCostUsd: modelCalls && !unpricedCalls ? knownCostUsd : null,
    pricing: modelSteps.find((step) => step.cost?.pricing)?.cost.pricing,
    totalMs: Number.isFinite(elapsed) ? Math.max(0, elapsed) : modelMs == null || toolMs == null ? null : modelMs + toolMs,
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

function readableTable(output) {
  const table = output?.table;
  if (!table?.rows?.length) return "";
  const names = table.columns?.map((column) => column.name) ?? Object.keys(table.rows[0]);
  const priority = ["site_id", "building_id", "company_id", "n_sites", "exposed_tiv_eur", "tiv_eur", "exposure_pct"];
  const selected = priority.filter((name) => names.includes(name));
  const columns = (selected.length ? selected : names).slice(0, 5);
  return `<h3>Returned data</h3><div class="trace-result-table"><table><thead><tr>${columns.map((name) => `<th>${escapeHtml(name)}</th>`).join("")}</tr></thead>
    <tbody>${table.rows.slice(0, 10).map((row) => `<tr>${columns.map((name) => `<td>${escapeHtml(String(row[name] ?? "Unavailable"))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}


function costDetails(step) {
  if (step.kind !== "model") return "";
  if (!hasCost(step)) return `<p class="trace-note">Cost unavailable: ${escapeHtml(step.cost?.reason ?? "Token usage or pricing was not recorded for this call.")}</p>`;
  const labels = { input: "Ordinary input", cache_read: "Cache reads", cache_write_30m: "Cache writes · 30 min",
    cache_write_12h: "Cache writes · 12 h", output: "Output (includes reasoning)" };
  const rows = step.cost.components.map((part) => `<tr><th scope="row">${escapeHtml(labels[part.kind] ?? part.kind)}</th>
    <td>${count.format(part.tokens)}</td><td>$${rate.format(part.rate_per_million)}</td><td>${dollars(part.cost_usd)}</td></tr>`).join("");
  return `<h3>Estimated API cost · USD</h3>
    <div class="trace-cost-breakdown"><table><thead><tr><th>Tokens</th><th>Count</th><th>USD / 1M</th><th>Cost</th></tr></thead>
    <tbody>${rows}</tbody></table></div>
    ${step.cost.long_context ? '<p class="trace-note">Long prompt rates apply to the full request: 2× input/cache and 1.5× output.</p>' : ""}
    ${step.cost.note ? `<p class="trace-note">${escapeHtml(step.cost.note)}</p>` : ""}`;
}

function costSummary(trace) {
  return `<div class="trace-cost-total">
    <span>Estimated total API cost · USD</span><strong>${dollars(trace.totalCostUsd)}</strong>
  </div>`;
}

function pricingDetails(trace) {
  const pricing = trace.pricing;
  const rates = pricing?.rates_per_million;
  return `${trace.unpricedCalls ? `<p class="trace-note">${trace.unpricedCalls} model call(s) have no cost estimate.${trace.modelCalls > trace.unpricedCalls
      ? ` Known calls subtotal: ${dollars(trace.knownCostUsd)}.` : ""}</p>` : ""}
    ${rates ? `<details class="trace-pricing"><summary>${escapeHtml(pricing.model)} · ${escapeHtml(pricing.tier)} public API prices</summary>
      <p>USD per million tokens: input $${rates.input}, cache reads $${rates.cache_read},
        cache writes $${rates.cache_write_30m} (30 min) / $${rates.cache_write_12h} (12 h), output $${rates.output}.</p>
      <p>Public API equivalent; your provider’s invoice may differ. Local tools have no model API charge.
        Prices checked ${escapeHtml(pricing.checked_on)} · <a href="https://developers.openai.com/api/docs/models/gpt-6-luna" target="_blank" rel="noopener noreferrer">Published prices</a>.</p>
      </details>` : ""}`;
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
      <span class="trace-step-metrics"><span class="trace-duration">${duration(step.durationMs)}</span>
        ${step.kind === "model" ? `<small class="trace-call-cost">${dollars(hasCost(step) ? step.cost.total_usd : null)}</small>` : ""}</span>
      <span class="trace-chevron" aria-hidden="true">›</span>
    </summary>
    <div class="trace-step-details">
      ${costDetails(step)}
      ${step.kind === "tool" ? readableTable(step.output) : ""}${rowsNote}
      <details class="trace-raw"><summary>${step.kind === "model" ? "Request metadata and response" : "Arguments and raw result"}</summary>
        <h3>${step.kind === "model" ? "Request metadata" : "Arguments"}</h3>
        <pre>${escapeHtml(jsonPreview(step.input))}</pre>
        <h3>Output preview</h3><pre>${escapeHtml(jsonPreview(outputPreview(step.output)))}</pre>
      </details>
    </div>
  </details></li>`;
}

function traceHtml(message, response) {
  const trace = buildTrace(response);
  const context = `<p class="trace-question">${escapeHtml(message)}</p>`;
  if (!trace.steps.length) return `${context}<p class="trace-empty">No execution steps were recorded for this response.</p>`;
  const timedMs = trace.modelMs == null || trace.toolMs == null ? null : trace.modelMs + trace.toolMs;
  const modelPercent = timedMs > 0 ? 100 * trace.modelMs / timedMs : 0;
  const tokens = trace.inputTokens || trace.outputTokens
    ? ` · ${count.format(trace.inputTokens)} input / ${count.format(trace.outputTokens)} output tokens` : "";
  return `${context}
    <div class="trace-stats">
      <div><span>Total agent time</span><strong>${duration(trace.totalMs)}</strong></div>
      <div><span>Model</span><strong>${duration(trace.modelMs)}</strong></div>
      <div><span>Tools</span><strong>${duration(trace.toolMs)}</strong></div>
      ${costSummary(trace)}
    </div>
    ${pricingDetails(trace)}
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
  button.textContent = "Show trace";
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
