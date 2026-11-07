// Renders 06_pitch_deck/src/animated.html frame by frame in headless Chrome (1920x1080).
//   node render_anim.mjs <out_dir> [fps=30] [only=t1,t2,...]
// Writes <out_dir>/NNNNN.jpg for t = 0, 1/fps, ... < END. With "only", writes stills at those times.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, mkdtempSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const OUT = resolve(process.argv[2]);
const FPS = +(process.argv[3] || 30);
const ONLY = process.argv[4] ? process.argv[4].split(",").map(Number) : null;
const HERE = dirname(fileURLToPath(import.meta.url));
const PAGE = "file://" + resolve(HERE, "../06_pitch_deck/src/animated.html") + "?capture=1";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9334;
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = mkdtempSync(join(tmpdir(), "anim-rec-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--window-size=1920,1080", "--hide-scrollbars", "--force-device-scale-factor=1", "--allow-file-access-from-files", "about:blank"], { stdio: "ignore" });
let targets;
for (let i = 0; i < 50 && !targets; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); } catch { await sleep(200); }
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let seq = 0; const pending = new Map();
ws.addEventListener("message", (m) => { const msg = JSON.parse(m.data); if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); } });
const send = (method, params = {}) => { const id = ++seq; ws.send(JSON.stringify({ id, method, params })); return new Promise((r) => pending.set(id, r)); };
const js = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;

await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: PAGE });
for (let i = 0; i < 100; i++) { if (await js(`document.readyState === "complete" && typeof render === "function" && [...document.images].every(i => i.complete)`)) break; await sleep(100); }
await js(`document.fonts.ready.then(() => true)`);
const END = await js("END");
const times = ONLY || Array.from({ length: Math.round(END * FPS) }, (_, i) => i / FPS);
const t0 = Date.now();
for (let i = 0; i < times.length; i++) {
  await js(`render(${times[i]})`);
  const PNG = process.env.FORMAT === "png";
  const shot = await send("Page.captureScreenshot", PNG ? { format: "png", fromSurface: true } : { format: "jpeg", quality: 94, fromSurface: true });
  const name = ONLY ? `t${times[i].toFixed(2)}.${PNG ? "png" : "jpg"}` : `${String(i).padStart(5, "0")}.jpg`;
  writeFileSync(join(OUT, name), Buffer.from(shot.result.data, "base64"));
  if (i % 300 === 0) console.log(`${i}/${times.length} frames, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
}
console.log(`done: ${times.length} frames in ${((Date.now() - t0) / 1000).toFixed(0)} s, END ${END}`);
ws.close(); chrome.kill(); process.exit(0);
