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

// Lobbies: ?lobby= picks one; otherwise ask once. A new name creates a lobby with its own world.
function lobbyName() {
  const params = new URLSearchParams(location.search);
  let lobby = (params.get("lobby") || "").trim();
  if (!lobby) {
    lobby = (prompt("Lobby to join or create (blank = main)?") || "").trim() || "main";
    params.set("lobby", lobby);
    params.set("name", MY_NAME);
    history.replaceState(null, "", `${location.pathname}?${params}`);   // the URL is shareable
  }
  return lobby.toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 24) || "main";
}
const MY_LOBBY = lobbyName();
// Same origin when the page comes from the game server itself (single-port / hosted, https -> wss);
// the classic two-port setup (page on :8000) talks to :8765. ?server=host:port points at any server.
const QS = `?name=${encodeURIComponent(MY_NAME)}&lobby=${encodeURIComponent(MY_LOBBY)}`;
const SERVER = new URLSearchParams(location.search).get("server");
const WS_URL = SERVER
  ? `${SERVER.startsWith("ws") ? SERVER : (location.protocol === "https:" ? "wss://" : "ws://") + SERVER}/${QS}`
  : location.port === "8000" || location.protocol === "file:"
    ? `ws://${location.hostname || "127.0.0.1"}:8765/${QS}`
    : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/${QS}`;

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
  return p;
}

function addText(className, text) {
  return addLine(className, (p) => { p.textContent = text; });
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

function showStatus(msg) {
  if (msg.player && msg.player !== MY_NAME) return; // private to this player
  const box = document.getElementById("player-status");
  const max = Number(msg.max) > 0 ? Number(msg.max) : 10;
  const hp = Math.max(0, Math.min(max, Number(msg.hp) || 0));
  const ratio = hp / max;
  const fill = document.getElementById("hp-fill");
  fill.style.width = `${ratio * 100}%`;
  fill.style.background = `hsl(${Math.round(ratio * 120)}, 65%, 45%)`; // green -> red
  showRespawn(msg.hp <= 0);
  const hpText = document.getElementById("hp-text");
  hpText.textContent = hp <= 0 ? "You are dead" : `${hp}/${max}`;
  hpText.classList.toggle("dead", hp <= 0);
  renderInventory(Array.isArray(msg.inventory) ? msg.inventory : []);
  box.hidden = false;
}

// Inventory overlay: read-only list of carried items (actions still go through chat).
const invButton = document.getElementById("inv-button");
const invOverlay = document.getElementById("inv-overlay");

function renderInventory(items) {
  document.getElementById("inv-count").textContent = items.length;
  const list = document.getElementById("inv-list");
  list.replaceChildren();
  if (!items.length) {
    const li = document.createElement("li");
    li.className = "inv-empty";
    li.textContent = "You are carrying nothing.";
    list.appendChild(li);
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  }
}

function setInventoryOpen(open) {
  invOverlay.hidden = !open;
  invButton.setAttribute("aria-expanded", String(open));
  if (!open) input.focus();
}

invButton.addEventListener("click", () => setInventoryOpen(invOverlay.hidden));
document.getElementById("inv-close").addEventListener("click", () => setInventoryOpen(false));
invOverlay.addEventListener("click", (event) => {
  if (event.target === invOverlay) setInventoryOpen(false); // click outside the panel
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !invOverlay.hidden) setInventoryOpen(false);
});
renderInventory([]);

let worldId = null;
function showMessage(msg) {
  if (msg.type === "world") {
    // A new server start means a fresh world: clear the old log and stats.
    if (worldId !== null && worldId !== msg.id) {
      log.innerHTML = "";
      showStatus({ hp: 10, max: 10, inventory: [] });
      addText("system", "The world has been reset.");
    }
    worldId = msg.id;
    if (msg.lobby) document.title = `Zoairk · ${msg.lobby}`;
    if (msg.lobby) setStatus(`connected · lobby ${msg.lobby}`, true);
    return;
  }
  if (msg.type === "status") { showStatus(msg); return; }
  if (msg.type === "switch_scene") {
    // The header shows only the room; the description is a grey event in the log (team feedback).
    sceneName.textContent = msg.scene.replace(/_/g, " ");
    sceneDescription.textContent = "";
    addText("scene-break", msg.scene.replace(/_/g, " "));
    if (window.Fx) Fx.scene(msg.description);
    return;
  }
  if (msg.type !== "message") return;
  if (msg.role === "player") {
    if (msg.player !== MY_NAME) addText("player", `${msg.player}: ${msg.text}`); // others' moves
    return;
  }
  if (msg.role === "scene") {               // room description: a grey event in the log
    addText("scene-desc", msg.text);
    if (window.Fx) Fx.scene(msg.text);
    return;
  }
  if (msg.role === "npc") showNpcMessage(msg);
  else if (msg.role === "system") addText("system", msg.text);
  else {
    const line = addText("narrator", msg.text);
    if (window.Fx) Fx.play(msg.effects, line, msg.text, !msg.hit || msg.hit === MY_NAME);
  }
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
  if (window.Fx) Fx.unlock(); // audio may only start from a user gesture

  addText("player", text);
  socket.send(JSON.stringify({ type: "send_message", text }));
  input.value = "";
  pending += 1;
  setThinking(true);
});

const muteBtn = document.getElementById("mute");
function renderMute() {
  const m = window.Fx ? Fx.isMuted() : false;
  // Say the current state in words (team feedback: the icon alone was ambiguous).
  muteBtn.textContent = m ? "🔇 Sound off" : "🔊 Sound on";
  muteBtn.title = m ? "Sound is off. Click to turn it on." : "Sound is on. Click to turn it off.";
  muteBtn.setAttribute("aria-label", muteBtn.title);
}
if (muteBtn && window.Fx) {
  renderMute();
  muteBtn.addEventListener("click", () => {
    Fx.unlock();
    Fx.setMuted(!Fx.isMuted());
    renderMute();
    input.focus();
  });
}

connect();


// Respawn: shown only while dead; sends the "respawn" command through the normal chat channel.
function showRespawn(dead) {
  let btn = document.getElementById("respawn-btn");
  if (!btn) {
    btn = document.createElement("button");
    btn.id = "respawn-btn";
    btn.type = "button";
    btn.textContent = "↻ Respawn";
    btn.addEventListener("click", () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "send_message", text: "respawn" }));
      }
    });
    const hp = document.getElementById("hp-text");
    (hp && hp.parentElement ? hp.parentElement : document.body).appendChild(btn);
  }
  btn.hidden = !dead;
}


// Invite: a QR code (made by the server) for this lobby's link, so others can scan and join.
const API_BASE = location.port === "8000" ? `http://${location.hostname || "127.0.0.1"}:8765` : location.origin;
const inviteOverlay = document.getElementById("invite-overlay");
const inviteUrl = document.getElementById("invite-url");
const inviteWarn = document.getElementById("invite-warn");
async function openInvite() {
  inviteOverlay.hidden = false;
  document.getElementById("invite-qr").textContent = "making QR code…";
  try {
    const res = await fetch(`${API_BASE}/invite?lobby=${encodeURIComponent(MY_LOBBY)}`);
    const data = await res.json();
    document.getElementById("invite-qr").innerHTML = data.svg || "";
    if (!data.svg) document.getElementById("invite-qr").textContent = "(QR code unavailable — share the link)";
    inviteUrl.textContent = data.url;
    inviteUrl.href = data.url;
    inviteWarn.hidden = data.reachable;
    inviteWarn.textContent = data.reachable ? "" :
      "This link only works on this computer. Start the server with ZOAIRK_HOST=0.0.0.0 (same Wi-Fi) or set ZOAIRK_PUBLIC_URL (domain or tunnel) so others can join.";
  } catch (err) {
    document.getElementById("invite-qr").textContent = "Couldn't reach the server for an invite.";
  }
}
document.getElementById("invite").addEventListener("click", openInvite);
document.getElementById("invite-close").addEventListener("click", () => { inviteOverlay.hidden = true; });
inviteOverlay.addEventListener("click", (event) => { if (event.target === inviteOverlay) inviteOverlay.hidden = true; });
document.addEventListener("keydown", (event) => { if (event.key === "Escape") inviteOverlay.hidden = true; });
document.getElementById("invite-copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(inviteUrl.href); document.getElementById("invite-copy").textContent = "Copied"; }
  catch (e) { document.getElementById("invite-copy").textContent = "Copy failed"; }
});
