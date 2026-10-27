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
const inline = (line) => line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
const isTableRow = (line) => /^\s*\|.*\|\s*$/.test(line);
const isSeparator = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);

// Pipe tables: a header row, a |---|---:| separator (colons set alignment), then body rows.
function tableHtml(lines) {
  const align = cells(lines[1]).map((c) => (c.endsWith(":") ? "right" : c.startsWith(":") ? "center" : "left"));
  const row = (line, tag) => `<tr>${cells(line).map((c, i) =>
    `<${tag} style="text-align:${align[i] ?? "left"}">${inline(c)}</${tag}>`).join("")}</tr>`;
  return `<div class="md-table"><table><thead>${row(lines[0], "th")}</thead>` +
    `<tbody>${lines.slice(2).map((l) => row(l, "td")).join("")}</tbody></table></div>`;
}

export function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  const out = [];
  let inList = false;
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    if (isTableRow(raw) && i + 1 < lines.length && isSeparator(lines[i + 1])) {
      if (inList) { out.push("</ul>"); inList = false; }
      let j = i + 2;
      while (j < lines.length && isTableRow(lines[j])) j++;
      out.push(tableHtml(lines.slice(i, j)));
      i = j - 1;
      continue;
    }
    const line = inline(raw);
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
