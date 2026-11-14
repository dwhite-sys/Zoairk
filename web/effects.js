// Zoairk effects: synthesized sounds (Web Audio, no files) and small visual cues
// for narrator "effects" (docs/contracts.md C4). Exposes window.Fx.

(function () {
  const FIRE_RE = /is (open and )?on fire/i;
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let ctx = null;
  let master = null;
  let noiseBuffer = null;
  let crackle = null; // {src, gain, timer} while fire sound is running
  let burning = false;
  let muted = false;
  try { muted = localStorage.getItem("zoairk-muted") === "1"; } catch (e) {}

  // --- audio plumbing -------------------------------------------------------

  // Called from a user gesture (send / Enter / mute click) to satisfy autoplay rules.
  function unlock() {
    try {
      if (!ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return;
        ctx = new AC();
        master = ctx.createGain();
        master.gain.value = muted ? 0 : 0.35;
        master.connect(ctx.destination);
        noiseBuffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
        const d = noiseBuffer.getChannelData(0);
        for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
      }
      if (ctx.state === "suspended") ctx.resume();
      if (burning && !crackle) startCrackle();
    } catch (e) { console.warn("audio unavailable", e); }
  }

  function ready() { return ctx && ctx.state === "running"; }

  function noise(dur, filterType, freq, vol, freqEnd) {
    const t = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    const f = ctx.createBiquadFilter();
    f.type = filterType;
    f.frequency.setValueAtTime(freq, t);
    if (freqEnd) f.frequency.exponentialRampToValueAtTime(freqEnd, t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f).connect(g).connect(master);
    src.start(t);
    src.stop(t + dur + 0.05);
  }

  function tone(type, f0, f1, dur, vol) {
    const t = ctx.currentTime;
    const o = ctx.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(f0, t);
    o.frequency.exponentialRampToValueAtTime(f1, t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(master);
    o.start(t);
    o.stop(t + dur + 0.05);
  }

  const sounds = {
    hit() { noise(0.12, "lowpass", 1200, 0.8); tone("sine", 160, 45, 0.25, 0.9); },
    shatter() { noise(0.5, "highpass", 3000, 0.7); noise(0.25, "bandpass", 6000, 0.4); },
    throw() { noise(0.35, "bandpass", 400, 0.5, 2500); },
    open() { tone("triangle", 220, 320, 0.25, 0.25); noise(0.05, "highpass", 2000, 0.3); },
    close() { tone("triangle", 260, 140, 0.18, 0.3); noise(0.06, "lowpass", 600, 0.6); },
    read() { noise(0.15, "highpass", 2500, 0.25); setTimeout(() => ready() && noise(0.2, "highpass", 3500, 0.2), 140); },
    extinguish() { noise(1.2, "highpass", 6000, 0.5, 400); },
    fire() { noise(0.4, "lowpass", 900, 0.6); },
    ash() { noise(0.6, "lowpass", 500, 0.35, 150); setTimeout(() => ready() && noise(0.3, "lowpass", 300, 0.2), 200); },
  };

  function startCrackle() {
    if (!ready() || crackle) return;
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer;
    src.loop = true;
    const f = ctx.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.value = 700;
    const gain = ctx.createGain();
    gain.gain.value = 0.12;
    src.connect(f).connect(gain).connect(master);
    src.start();
    // random pops
    const timer = setInterval(() => {
      if (!ready() || Math.random() < 0.35) return;
      noise(0.02 + Math.random() * 0.03, "highpass", 1500 + Math.random() * 3000, 0.25 + Math.random() * 0.3);
    }, 90);
    crackle = { src, gain, timer };
  }

  function stopCrackle() {
    if (!crackle) return;
    const c = crackle;
    crackle = null;
    clearInterval(c.timer);
    try {
      c.gain.gain.setTargetAtTime(0, ctx.currentTime, 0.3);
      c.src.stop(ctx.currentTime + 1.5);
    } catch (e) {}
  }

  // --- visuals --------------------------------------------------------------

  const glow = document.createElement("div");
  glow.id = "fire-glow";
  glow.className = "fire-glow";
  glow.setAttribute("aria-hidden", "true");
  document.body.appendChild(glow);

  function setBurning(on) {
    if (on === burning) return;
    burning = on;
    if (on) {
      glow.classList.remove("smoke");
      glow.classList.add("on");
      startCrackle();
    } else {
      glow.classList.remove("on");
      glow.classList.add("smoke");
      setTimeout(() => glow.classList.remove("smoke"), 2200);
      stopCrackle();
    }
  }

  function flash(el, cls) {
    if (!el) return;
    el.classList.remove(cls);
    void el.offsetWidth; // restart animation
    el.classList.add(cls);
  }

  function shake() {
    if (reduceMotion) return;
    const g = document.querySelector(".game");
    if (!g) return;
    flash(g, "fx-shake");
    setTimeout(() => g.classList.remove("fx-shake"), 350);
  }

  // --- public API -----------------------------------------------------------

  // Apply a narrator message's effects list; `lineEl` is the rendered log line.
  function play(effects, lineEl, text) {
    const list = Array.isArray(effects) ? effects : [];
    for (const name of list) {
      if (ready() && sounds[name]) {
        try { sounds[name](); } catch (e) {}
      }
      if (name === "fire") { flash(lineEl, "fx-fire"); setBurning(true); }
      else if (name === "extinguish" || name === "ash") { flash(lineEl, "fx-smoke"); setBurning(false); }
      else if (name === "hit") { flash(lineEl, "fx-hit"); shake(); }
      else if (name === "shatter") { flash(lineEl, "fx-shatter"); flash(document.body, "fx-white"); }
    }
    // "look" narration that describes something burning also lights the room.
    if (!list.includes("extinguish") && !list.includes("ash") && text && FIRE_RE.test(text)) setBurning(true);
  }

  // Scene description for the player's room: fire state follows it.
  function scene(description) {
    setBurning(FIRE_RE.test(description || ""));
  }

  function setMuted(m) {
    muted = m;
    try { localStorage.setItem("zoairk-muted", m ? "1" : "0"); } catch (e) {}
    if (master) master.gain.value = m ? 0 : 0.35;
  }

  window.Fx = { unlock, play, scene, setMuted, isMuted: () => muted, isBurning: () => burning };
})();
