import { api } from "./api.js";
import { escapeHtml, renderMarkdown } from "./format.js";
import { applyMapActions } from "./map.js";
import { renderResults } from "./results.js";

export function initChat({ getSessionId }) {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const send = document.getElementById("send");

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  for (const button of document.querySelectorAll(".suggestions button")) {
    button.addEventListener("click", () => { input.value = button.textContent; form.requestSubmit(); });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled) return;
    input.value = "";
    send.disabled = true;
    setEmptyState(false);
    addMessage("user", escapeHtml(message));
    const pending = addMessage("assistant pending", "Working on it");
    try {
      const response = await api.chat(getSessionId(), message);
      pending.remove();
      const msg = addMessage("assistant", renderMarkdown(response.reply));
      msg.append(renderResults(response.results));
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
