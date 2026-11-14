// Zoairk browser client. Talks to server.py over the C4 WebSocket protocol
// (docs/contracts.md). No framework: plain DOM functions.

// Multiplayer: everyone shares one world; pick a name once (kept per browser; ?name= overrides).
function playerName() {
  const fromUrl = new URLSearchParams(location.search).get("name");
  let saved = null;
  try { saved = localStorage.getItem("zoairk-name"); } catch (e) {}
  let name = (fromUrl || saved || "").trim();
  if (!name) name = (prompt("Your name?") || "").trim() || "Player";
  try { localStorage.setItem("zoairk-name", name); } catch (e) {}
  return name.slice(0, 24);
}
const MY_NAME = playerName();
const WS_URL = `ws://${location.hostname || "127.0.0.1"}:8765/?name=${encodeURIComponent(MY_NAME)}`;

const log = document.getElementById("log");
const form = document.getElementById("input-form");
const input = document.getElementById("input");
const thinking = document.getElementById("thinking");
const statusEl = document.getElementById("status");
const sceneName = document.getElementById("scene-name");
const sceneDescription = document.getElementById("scene-description");

let socket = null;
let pending = 0; // inputs sent that have not had a reply yet
let retryDelay = 500;

function addLine(className, build) {
  const p = document.createElement("p");
  p.className = `line ${className}`;
  build(p);
  log.appendChild(p);
  log.scrollTop = log.scrollHeight;
}

function addText(className, text) {
  addLine(className, (p) => { p.textContent = text; });
}

function showNpcMessage(msg) {
  addLine("npc", (p) => {
    const name = document.createElement("span");
    name.className = "npc-name";
    name.textContent = msg.npc || "Someone";
    p.appendChild(name);

    if (msg.decision) {
      const badge = document.createElement("span");
      badge.className = `badge ${msg.decision}`;
      const pct = typeof msg.confidence === "number"
        ? ` ${Math.round(msg.confidence <= 1 ? msg.confidence * 100 : msg.confidence)}%`
        : "";
      badge.textContent = msg.decision + pct;
      p.appendChild(badge);
    }

    p.appendChild(document.createTextNode(": " + msg.text));
  });
}

function showMessage(msg) {
  if (msg.type === "switch_scene") {
    sceneName.textContent = msg.scene;
    sceneDescription.textContent = msg.description || "";
    addText("scene-break", msg.scene);
    return;
  }
  if (msg.type !== "message") return;
  if (msg.role === "player") {
    if (msg.player !== MY_NAME) addText("player", `${msg.player}: ${msg.text}`); // others' moves
    return;
  }
  if (msg.role === "npc") showNpcMessage(msg);
  else if (msg.role === "system") addText("system", msg.text);
  else addText("narrator", msg.text);
}

function setThinking(on) {
  thinking.hidden = !on;
}

function setStatus(text, online) {
  statusEl.textContent = text;
  statusEl.classList.toggle("online", online);
  input.disabled = !online;
  form.querySelector("button").disabled = !online;
}

function connect() {
  setStatus("connecting…", false);
  socket = new WebSocket(WS_URL);

  socket.onopen = () => {
    retryDelay = 500;
    setStatus("connected", true);
    input.focus();
  };

  socket.onmessage = (event) => {
    // One player input can produce several messages; we hide "thinking…"
    // as soon as the first reply arrives.
    if (pending > 0) pending = 0;
    setThinking(false);
    try {
      showMessage(JSON.parse(event.data));
    } catch (err) {
      console.error("bad message", event.data, err);
    }
  };

  socket.onclose = () => {
    pending = 0;
    setThinking(false);
    setStatus("reconnecting…", false);
    setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 5000);
  };
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value;
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  if (text.trim() === "") return; // blank input does nothing (no turn)

  addText("player", text);
  socket.send(JSON.stringify({ type: "send_message", text }));
  input.value = "";
  pending += 1;
  setThinking(true);
});

connect();
