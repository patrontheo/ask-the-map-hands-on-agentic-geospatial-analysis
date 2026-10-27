import { initChat } from "./chat.js";
import { initMap, showOverview } from "./map.js";
import { initTrace } from "./trace.js";

// A reload starts a fresh transcript and map, so it also starts a fresh conversation.
const sessionId = crypto.randomUUID();
initTrace();
initChat({ getSessionId: () => sessionId });
initMap("map").then(showOverview).catch((err) => {
  const notice = document.getElementById("map-notice");
  notice.textContent = `Map failed to load: ${err.message}`;
  notice.hidden = false;
});
