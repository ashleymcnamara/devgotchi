(() => {
  "use strict";
  const REPO = "ashleymcnamara/devgotchi";
  const RAW = `https://raw.githubusercontent.com/${REPO}/main/`;
  const STORE = "devgotchi:v1";
  const VERB = { coffee: "poured Byte a coffee", nap: "sent Byte to bed", debug: "squashed a bug with Byte" };
  const SAY = { coffee: "☕ Coffee's brewing…", nap: "💤 Tucking Byte in…", debug: "🐛 Hunting the bug…" };
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s) => document.querySelector(s);
  const lcd = $("#lcd"), msg = $("#msg"), device = $("#device");
  const buttons = [...document.querySelectorAll(".btn")];
  let urls = {}, busy = false, status = null;

  const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
  const save = (v) => { try { localStorage.setItem(STORE, JSON.stringify({ ...load(), ...v })); } catch {} };
  const ago = (ms) => {
    const m = Math.round(ms / 60000);
    if (m < 60) return `${Math.max(1, m)} min ago`;
    const h = Math.round(m / 60);
    return h < 48 ? `${h}h ago` : `${Math.round(h / 24)} days ago`;
  };

  async function screen(name) {
    const r = await fetch(`${RAW}egg/${name}.svg?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    const doc = new DOMParser().parseFromString(await r.text(), "image/svg+xml");
    const svg = doc.documentElement;
    if (svg.nodeName !== "svg" || doc.querySelector("script, foreignObject")) throw new Error("bad svg");
    svg.removeAttribute("width"); svg.removeAttribute("height");
    lcd.replaceChildren(document.importNode(svg, true));
    lcd.setAttribute("aria-label", svg.getAttribute("aria-label") || "Byte's screen");
  }

  function press(id) {
    if (busy || !urls[id]) return;
    busy = true;
    const btn = buttons.find((b) => b.dataset.do === id);
    device.classList.add("busy");
    btn.classList.add("down");
    buttons.forEach((b) => (b.disabled = true));
    msg.textContent = SAY[id];
    save({ last: id, at: Date.now() });
    const go = () => {
      msg.textContent = "Opening GitHub. Hit Create and Byte replies in about 30 seconds.";
      location.assign(urls[id]);
    };
    screen(`lcd-${id}`).then(() => {
      lcd.classList.remove("flash"); void lcd.offsetWidth; lcd.classList.add("flash", "hop");
    }).catch(() => {}).finally(() => setTimeout(go, reduced ? 250 : 1300));
    setTimeout(() => btn.classList.remove("down"), 160);
  }

  function reset() {
    busy = false;
    device.classList.remove("busy");
    lcd.classList.remove("hop", "flash");
    buttons.forEach((b) => { b.disabled = false; b.classList.remove("down"); });
    const me = load();
    const back = me.last ? `Welcome back! You ${VERB[me.last] || "visited"} ${ago(Date.now() - me.at)}. ` : "";
    msg.textContent = back + (status ? status.why : "Press a button to take care of Byte.");
    buttons.forEach((b) => b.classList.toggle("need", !!status && b.dataset.do === status.need));
    screen("lcd").catch(() => { lcd.setAttribute("aria-label", "Byte's screen couldn't load"); });
  }

  async function caretakers() {
    try {
      const get = async (f) => (await fetch(`${RAW}${f}?t=${Date.now()}`, { cache: "no-store" })).json();
      const [st, s] = await Promise.all([get("state.json"), get("egg/status.json").catch(() => null)]);
      if (s && typeof s.why === "string") { status = s; if (!busy) reset(); }
      const ok = (u) => /^[A-Za-z0-9-]{1,39}$/.test(u);
      const top = (s && Array.isArray(s.recent) ? s.recent : []).filter(ok);
      const who = $("#who");
      const n = Object.keys(st.users || {}).length, t = st.total || 0;
      who.textContent = `${s && s.next ? `Byte ${s.next} · ` : ""}${n} caretaker${n === 1 ? '' : 's'} · ${t} press${t === 1 ? '' : 'es'}`;
      if (top.length) {
        who.append(" · recently: ");
        top.forEach((u, i) => {
          const a = document.createElement("a");
          a.href = `https://github.com/${u}`; a.textContent = `@${u}`;
          who.append(i ? " " : "", a);
        });
      }
    } catch {}
  }

  buttons.forEach((b) => b.addEventListener("click", () => press(b.dataset.do)));
  addEventListener("keydown", (e) => {
    const k = { c: "coffee", n: "nap", d: "debug" }[e.key.toLowerCase()];
    if (k && !e.metaKey && !e.ctrlKey && !e.altKey && document.activeElement === document.body) press(k);
  });
  addEventListener("pageshow", (e) => { if (e.persisted) reset(); });

  fetch("actions.json").then((r) => r.json()).then((cfg) => {
    cfg.buttons.forEach((b) => { if (b.url.startsWith(`https://github.com/${REPO}/issues/new?`)) urls[b.id] = b.url; });
    const want = new URLSearchParams(location.search).get("do");
    if (want) history.replaceState(null, "", location.pathname);
    reset();
    caretakers();
    if (urls[want]) setTimeout(() => press(want), reduced ? 0 : 500);
  });
})();
