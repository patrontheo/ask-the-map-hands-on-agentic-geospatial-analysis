async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json();
}

export const api = {
  layers: () => request("/api/layers"),
  layer: (url) => request(url),
  chat: (sessionId, message) =>
    request("/api/chat", { method: "POST", body: JSON.stringify({ session_id: sessionId, message }) }),
};
