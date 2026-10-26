import { escapeHtml, formatEur, formatNumber } from "./format.js";

// Renders tool results (tables) under an assistant answer. Results come from the backend, never from the model text.
export function renderResults(results) {
  const fragment = document.createDocumentFragment();
  for (const result of results) {
    if (result.status === "error") {
      fragment.append(details(`${result.tool}: error — ${result.error.message}`, `<p>${escapeHtml(result.error.hint)}</p>`, true));
    } else if (result.table && result.table.rows.length) {
      fragment.append(details(`${result.tool} · ${result.table.total_rows} row(s)`, tableHtml(result.table)));
    }
  }
  return fragment;
}

function details(title, inner, isError = false) {
  const el = document.createElement("details");
  el.className = `result${isError ? " error" : ""}`;
  el.innerHTML = `<summary>${escapeHtml(title)}</summary><div class="result-table-wrap">${inner}</div>`;
  return el;
}

const HEADERS = { group: "ID", group_name: "Name", n_sites: "Sites", tiv_eur: "TIV", site_id: "Site" };

function tableHtml(table) {
  const isNum = (c) => c.type === "number" || c.type === "integer";
  const head = table.columns
    .map((c) => `<th class="${isNum(c) ? "num" : ""}" title="${escapeHtml(c.name)}">${escapeHtml(HEADERS[c.name] ?? c.name)}</th>`)
    .join("");
  const body = table.rows.map((row) => `<tr>${table.columns.map((c) => {
    const v = row[c.name];
    const text = c.unit === "EUR" ? formatEur(v) : isNum(c) ? formatNumber(v) : v;
    return `<td class="${isNum(c) ? "num" : ""}">${escapeHtml(text)}</td>`;
  }).join("")}</tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}
