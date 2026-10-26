import { initChat } from "./chat.js";
import { initMap } from "./map.js";

const SESSION_KEY = "ask-the-map-session";

function sessionId() {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

initChat({ getSessionId: sessionId });
initMap("map").catch((err) => {
  const notice = document.getElementById("map-notice");
  notice.textContent = `Map failed to load: ${err.message}`;
  notice.hidden = false;
});
