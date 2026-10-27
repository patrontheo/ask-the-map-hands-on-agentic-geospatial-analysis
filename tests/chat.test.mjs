import assert from "node:assert/strict";
import test from "node:test";

function element(tagName = "div") {
  return {
    tagName, children: [], listeners: new Map(), innerHTML: "", value: "",
    append(...nodes) {
      for (const node of nodes) {
        if (node.tagName === "fragment") this.append(...node.children);
        else { node.parent = this; this.children.push(node); }
      }
    },
    remove() { this.parent.children = this.parent.children.filter((child) => child !== this); },
    addEventListener(name, callback) { this.listeners.set(name, callback); },
    setAttribute(name, value) { (this.attributes ??= new Map()).set(name, value); },
    focus() {},
  };
}

test("chat shows Markdown and follow-ups without raw tool cards, preserving trace data", async (t) => {
  const globals = ["document", "window", "fetch"];
  const original = new Map(globals.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  t.after(() => {
    for (const [key, descriptor] of original) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
  t.mock.method(console, "debug", () => {});
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  globalThis.document = { getElementById: get, createElement: element,
    createDocumentFragment: () => element("fragment"), querySelectorAll: () => [], addEventListener() {} };
  globalThis.window = new EventTarget();
  const response = {
    reply: "| Company | TIV |\n|---|---:|\n| Example | EUR 1M |",
    results: [
      { tool: "spatial_join", status: "ok", table: { total_rows: 1, columns: [{ name: "internal" }],
        rows: [{ internal: "RAW_TOOL_ROW" }] }, map_actions: [] },
      { tool: "calculate", status: "error", error: { message: "RAW_TOOL_ERROR", hint: "Internal hint" }, map_actions: [] },
      { tool: "suggest_follow_ups", status: "ok", data: { follow_ups: ["Which sites are affected?"] }, map_actions: [] },
    ],
    trace: [{ type: "tool_result", duration_ms: 2, payload: { result_id: "r_0001" } }],
  };
  globalThis.fetch = async () => ({ ok: true, json: async () => response });
  const turns = [];
  window.addEventListener("chat:turn", (event) => turns.push(event.detail));
  const { initChat } = await import("../frontend/js/chat.js");
  initChat({ getSessionId: () => "chat-test" });
  get("chat-input").value = "Which companies?";
  await get("chat-form").listeners.get("submit")({ preventDefault() {} });
  const messages = get("messages").children;
  assert.equal(messages.length, 2);
  const answer = messages[1];
  assert.match(answer.children[0].innerHTML, /<table>/);
  assert.equal(answer.children[1].className, "follow-ups");
  assert.equal(answer.children[1].children[0].textContent, "Which sites are affected?");
  const nodes = (node) => [node, ...node.children.flatMap(nodes)];
  assert.equal(nodes(answer).some((node) => node.tagName === "details"), false);
  assert.equal(nodes(answer).some((node) => /RAW_TOOL_ROW|RAW_TOOL_ERROR/.test(node.innerHTML)), false);
  assert.equal(turns.length, 1);
  assert.equal(turns[0].response, response);
  assert.equal(turns[0].response.results[0].table.rows[0].internal, "RAW_TOOL_ROW");
});
