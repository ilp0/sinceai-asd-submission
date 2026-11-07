// Records the demo dashboard in headless Chrome (1920x1080) with the DevTools screencast.
//   node record_demo.mjs <out_dir> [url]
// Writes <out_dir>/frames/NNNNN.jpg and <out_dir>/frames.ffconcat (per-frame durations).
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const OUT = process.argv[2];
const URL_ = process.argv[3] || "http://127.0.0.1:8797/";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;
mkdirSync(join(OUT, "frames"), { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = mkdtempSync(join(tmpdir(), "demo-rec-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--window-size=1920,1080", "--hide-scrollbars", "--force-device-scale-factor=1", "about:blank"], { stdio: "ignore" });

let targets;
for (let i = 0; i < 50 && !targets; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); } catch { await sleep(200); }
}
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let seq = 0; const pending = new Map(); const frames = [];
ws.addEventListener("message", (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg.result); pending.delete(msg.id); }
  if (msg.method === "Page.screencastFrame") {
    const { data, metadata, sessionId } = msg.params;
    const n = frames.length;
    writeFileSync(join(OUT, "frames", `${String(n).padStart(5, "0")}.jpg`), Buffer.from(data, "base64"));
    frames.push(metadata.timestamp);
    send("Page.screencastFrameAck", { sessionId });
  }
});
function send(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((r) => pending.set(id, r));
}
async function js(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  return r?.result?.value;
}
async function click(selectorExpr) {
  const box = await js(`(() => { const e = ${selectorExpr}; if (!e) return null; e.scrollIntoView({block:"nearest"}); const r = e.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; })()`);
  if (!box) throw new Error("not found: " + selectorExpr);
  // visible cursor: move to the target, then show a press ring
  await js(`window.__cursorTo(${box.x}, ${box.y})`);
  await sleep(750);
  await js(`window.__press()`);
  for (const type of ["mouseMoved", "mousePressed", "mouseReleased"])
    await send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: 1 });
  await sleep(300);
}
async function pointAt(selectorExpr, dx = 0) {
  const box = await js(`(() => { const e = ${selectorExpr}; if (!e) return null; e.scrollIntoView({block:"nearest"}); const r = e.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; })()`);
  if (box) await js(`window.__cursorTo(${box.x + dx}, ${box.y})`);
}
const caption = (t) => js(`window.__caption(${JSON.stringify(t)})`);
// Cursor and caption overlay. Fixed position, no pointer events, so the page layout and clicks do not change.
const BAND = 120;  // caption band at the bottom of the video, under the dashboard
const OVERLAY = `(() => {
  const st = document.createElement("style");
  st.textContent = \`
    #__cur{position:fixed;left:0;top:0;z-index:99999;pointer-events:none;transform:translate(960px,600px);
      transition:transform .7s cubic-bezier(.4,0,.2,1)}
    #__cur svg{display:block;filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
    #__ring{position:absolute;left:-38px;top:-38px;width:76px;height:76px;border-width:6px;border-radius:50%;border:4px solid #1f6feb;opacity:0}
    #__ring.on{animation:__r .55s ease-out}
    @keyframes __r{0%{transform:scale(.3);opacity:1}100%{transform:scale(1.5);opacity:0}}
    #__cap{position:fixed;left:0;right:0;bottom:0;height:${BAND}px;z-index:99998;pointer-events:none;
      background:#fff;color:#000;border-top:2px solid #c9d2dd;font:700 56px/${BAND}px Inter,system-ui,sans-serif;
      text-align:center;white-space:nowrap;transition:opacity .25s}
    #__cap.off{color:transparent}\`;
  document.head.appendChild(st);
  const c = document.createElement("div"); c.id = "__cur";
  c.innerHTML = '<div id="__ring"></div><svg width="58" height="68" viewBox="0 0 17 20"><path d="M1 1 L1 16 L5 12.5 L8 19 L10.6 17.8 L7.7 11.4 L13 11.4 Z" fill="#fff" stroke="#111" stroke-width="1.2" stroke-linejoin="round"/></svg>';
  document.documentElement.appendChild(c);
  const cap = document.createElement("div"); cap.id = "__cap"; cap.className = "off"; document.documentElement.appendChild(cap);
  window.__cursorTo = (x, y) => { c.style.transform = "translate(" + x + "px," + y + "px)"; };
  window.__press = () => { const r = document.getElementById("__ring"); r.classList.remove("on"); void r.offsetWidth; r.classList.add("on"); };
  window.__caption = (t) => { if (t) { cap.textContent = t; cap.classList.remove("off"); } else cap.classList.add("off"); };
})()`;
async function waitFor(expr, ms = 60000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await js(expr)) return; await sleep(200); }
  throw new Error("timeout: " + expr);
}

await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: URL_ });
await waitFor(`document.readyState === "complete" && typeof S !== "undefined" && S.alerts.length > 0`);
// CSS zoom 1.5 on the page: all UI text is 1.5x larger in the 1920x1080 video, readable on a phone.
// The overlay is outside <body>, so it is not zoomed.
await js(`document.body.style.zoom = "1.5"; document.body.style.height = "${(1080 - BAND) / 1.5}px"; document.documentElement.style.background = "#fff"`);
await js(OVERLAY);
await sleep(1500);
await send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
const t0 = Date.now(); const log = (s) => console.log(((Date.now() - t0) / 1000).toFixed(1) + "s", s);

// Demo run: PUMP-09 at 60 min/s from the start, one alert. The captions describe a live system.
// Alert: detection, model evidence, checked advice, one prepared question, Acknowledge. Then 3 s more.
const SPEED = process.env.SPEED || "60";
const bar = (word) => `[...document.querySelectorAll("#prob-bars .pb")].find(e => /${word}/i.test(e.textContent))`;
await js(`(() => { const s = document.getElementById("speed"); s.value = "${SPEED}"; s.dispatchEvent(new Event("change", {bubbles: true})); })()`);
await caption("Select the pump");
await sleep(2000);
await click(`document.querySelector('#assets .asset[data-id="PUMP-09"]')`);
await sleep(1500);
await caption("Timestral reads the last 3 h of all sensors every 10 s");
await pointAt(`document.getElementById("prob-chart")`);
await sleep(3500);
await click(`document.getElementById("play")`);
log("play at " + SPEED + " min/s");
await waitFor(`S.open && !S.ack.has(S.open)`, 180000);
const id = await js(`S.open`);
log("alert open " + id + " " + (await js(`S.alerts.find(a => a.id === S.open).fault_type`)));
await caption("Timestral detects misalignment: over 90 % for 15 min");
await pointAt(bar("misalignment"), -60);
await sleep(3000);
await sleep(3000);
await caption("The model shows its evidence: the strongest sensor signal");
await pointAt(`document.getElementById("m-evidence")`);
await sleep(3000);
await waitFor(`S.results[S.open] && S.results[S.open].status !== "running"`, 90000);
log("advice done: " + (await js(`S.results[S.open].status`)));
log("ask question: " + (await js(`document.querySelector("#chat-qs .qchip")?.textContent`)));
await caption("Ask a question about the alert");
await click(`document.querySelector("#chat-qs .qchip")`);
await waitFor(`(S.chats["${id}"] || []).length > 0 && !(S.chats["${id}"] || []).some(m => m.typing)`, 60000);
await sleep(2500);
log("acknowledge");
await caption("");
await click(`document.getElementById("m-close")`);
await waitFor(`S.open !== "${id}"`, 10000);
await sleep(1000);
await caption("Monitoring continues");
await sleep(2000);
log("end");
await send("Page.stopScreencast");
await sleep(500);

// ffconcat with per-frame durations from the screencast time stamps
let txt = "ffconcat version 1.0\n";
for (let i = 0; i < frames.length; i++) {
  const d = i + 1 < frames.length ? frames[i + 1] - frames[i] : 1 / 30;
  txt += `file 'frames/${String(i).padStart(5, "0")}.jpg'\nduration ${d.toFixed(4)}\n`;
}
txt += `file 'frames/${String(frames.length - 1).padStart(5, "0")}.jpg'\n`;
writeFileSync(join(OUT, "frames.ffconcat"), txt);
console.log(`frames ${frames.length}, span ${(frames.at(-1) - frames[0]).toFixed(1)} s`);
ws.close(); chrome.kill();
process.exit(0);
