export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

const eur = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

export function formatEur(value) {
  return value == null ? "" : eur.format(value);
}

export function formatNumber(value) {
  return value == null ? "" : num.format(value);
}

// Minimal, safe Markdown for model answers: escape first, then bold, inline code, bullet lists, line breaks.
export function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  const out = [];
  let inList = false;
  for (const raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
    const item = line.match(/^\s*[-*]\s+(.*)$/);
    if (item) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${item[1]}</li>`);
      continue;
    }
    if (inList) { out.push("</ul>"); inList = false; }
    out.push(line === "" ? "<br>" : `${line}<br>`);
  }
  if (inList) out.push("</ul>");
  return out.join("");
}
