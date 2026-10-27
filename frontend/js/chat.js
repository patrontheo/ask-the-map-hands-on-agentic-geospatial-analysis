import { api } from "./api.js";
import { escapeHtml, renderMarkdown } from "./format.js";
import { applyMapActions } from "./map.js";
import { PROMPT_GROUPS } from "./prompts.js";
import { renderResults } from "./results.js";

export function initChat({ getSessionId }) {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const send = document.getElementById("send");

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  const ask = (text) => { input.value = text; form.requestSubmit(); };
  for (const button of document.querySelectorAll(".suggestions button")) {
    button.addEventListener("click", () => ask(button.textContent));
  }
  initPromptLibrary(ask);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled) return;
    input.value = "";
    send.disabled = true;
    setEmptyState(false);
    for (const old of document.querySelectorAll(".follow-ups")) old.remove(); // only the latest answer offers follow-ups
    addMessage("user", escapeHtml(message));
    const pending = addMessage("assistant pending", "Working on it");
    try {
      const response = await api.chat(getSessionId(), message);
      pending.remove();
      const msg = addMessage("assistant", renderMarkdown(response.reply));
      msg.append(renderResults(response.results));
      msg.append(renderFollowUps(response.results, ask));
      try {
        for (const result of response.results) await applyMapActions(result.map_actions);
      } catch (mapErr) {
        console.warn("map action failed", mapErr);
      }
      // Hook for the trace pane (step-02): every turn's response, including its recorded trace events.
      window.dispatchEvent(new CustomEvent("chat:turn", { detail: { message, response } }));
      console.debug("trace", response.trace);
    } catch (err) {
      pending.remove();
      addMessage("assistant error", escapeHtml(`The request failed: ${err.message}`));
    } finally {
      send.disabled = false;
      input.focus();
    }
  });
}

// Follow-up questions the model offered through suggest_follow_ups; clicking one asks it.
function renderFollowUps(results, ask) {
  const questions = results.filter((r) => r.tool === "suggest_follow_ups" && r.status === "ok")
    .flatMap((r) => r.data.follow_ups ?? []);
  const fragment = document.createDocumentFragment();
  if (!questions.length) return fragment;
  const list = document.createElement("div");
  list.className = "follow-ups";
  for (const q of questions) {
    const button = Object.assign(document.createElement("button"), { type: "button", textContent: q });
    button.addEventListener("click", () => ask(q));
    list.append(button);
  }
  fragment.append(list);
  return fragment;
}

// Always-available example prompts. Picking one asks it straight away.
function initPromptLibrary(ask) {
  const panel = document.getElementById("prompt-library");
  const toggle = document.getElementById("library-toggle");
  panel.innerHTML = PROMPT_GROUPS.map((group) => `
    <section class="prompt-group">
      <h3>${escapeHtml(group.title)}</h3>
      ${group.hint ? `<p>${escapeHtml(group.hint)}</p>` : ""}
      <ul>${group.prompts.map((p) => `<li><button type="button">${escapeHtml(p)}</button></li>`).join("")}</ul>
    </section>`).join("");

  const setOpen = (open) => {
    panel.hidden = !open;
    if (open) panel.scrollTop = 0;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.classList.toggle("open", open);
  };
  toggle.addEventListener("click", () => setOpen(panel.hidden));
  panel.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    setOpen(false);
    ask(button.textContent);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) setOpen(false); });
  document.addEventListener("click", (e) => {
    if (!panel.hidden && !panel.contains(e.target) && !toggle.contains(e.target)) setOpen(false);
  });
}

function setEmptyState(visible) {
  document.getElementById("empty-state").hidden = !visible;
}

function addMessage(kind, html) {
  const li = document.createElement("li");
  li.className = `msg ${kind}`;
  const body = document.createElement("div");
  body.className = "body";
  body.innerHTML = html;
  li.append(body);
  const list = document.getElementById("messages");
  list.append(li);
  list.scrollTop = list.scrollHeight;
  return li;
}
