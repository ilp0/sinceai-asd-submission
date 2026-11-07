"use strict";
// RETROFIT AI demo dashboard: replay of two pumps, raw stream, alerts and the verified-guide pipeline.

const $ = (id) => document.getElementById(id);
const Q = new URLSearchParams(location.search);
const OPT = { inject: Q.get("test") === "1", pauseOnAlert: Q.get("pause") !== "0" };
// replaces the content only when it changed, so clicks and hover states survive the replay frames
const setHTML = (el, html) => { if (el._html !== html) { el._html = html; el.innerHTML = html; } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PUMPS = ["PUMP-08", "PUMP-09"];
const FAULT_NAME = {
  SUCTION_STRAINER_CLOGGING: "Suction strainer clogging", CAVITATION: "Pump cavitation",
  DISCHARGE_RESTRICTION: "Discharge-side restriction", BEARING_WEAR: "Bearing wear",
  MISALIGNMENT: "Pump–motor shaft misalignment", IMBALANCE: "Impeller imbalance", IMPELLER_WEAR: "Impeller wear",
  AIR_ENTRAINMENT: "Air entrainment in the water", SENSOR_DRIFT: "Sensor drift", SENSOR_STUCK: "Stuck sensor value",
  SENSOR_CALIBRATION_SHIFT: "Sensor calibration shift", SENSOR_NOISE_SPIKES: "Sensor noise spikes",
  COMMUNICATION_LOSS: "Gateway communication loss",
};
// fixed order of the probability rows: machine faults, then sensor and communication faults
const FAULT_ORDER = Object.keys(FAULT_NAME);
const SIGNAL_NAME = {
  flow_m3_h: "flow", suction_pressure_kpa: "suction pressure", discharge_pressure_kpa: "discharge pressure",
  motor_speed_rpm: "motor speed", motor_current_a: "motor current", motor_power_kw: "motor power",
  vibration_rms_mm_s: "vibration velocity", vibration_accel_rms_g: "vibration acceleration",
  vibration_crest_factor: "vibration crest factor", bearing_temp_c: "bearing temperature",
  motor_winding_temp_c: "winding temperature", fluid_temp_c: "fluid temperature", ambient_temp_c: "ambient temperature",
  comm_loss_flag: "data gaps (gateway)",
};
const SHORT = {
  flow_m3_h: "Q", suction_pressure_kpa: "Ps", discharge_pressure_kpa: "Pd", motor_speed_rpm: "n", motor_current_a: "I",
  motor_power_kw: "P", vibration_rms_mm_s: "v", vibration_accel_rms_g: "a", vibration_crest_factor: "cf",
  bearing_temp_c: "Tb", motor_winding_temp_c: "Tw", fluid_temp_c: "Tf", ambient_temp_c: "Ta",
};
const KPI_KEYS = ["flow_m3_h", "suction_pressure_kpa", "discharge_pressure_kpa", "motor_speed_rpm", "motor_current_a",
  "motor_power_kw", "vibration_rms_mm_s", "vibration_crest_factor", "bearing_temp_c"];
// one fixed color for each fault type, so a line keeps its color
const FAULT_COLOR = {
  BEARING_WEAR: "#d23434", SUCTION_STRAINER_CLOGGING: "#1f6feb", CAVITATION: "#0e7490", DISCHARGE_RESTRICTION: "#b7791f",
  MISALIGNMENT: "#8e44ad", IMBALANCE: "#14894a", IMPELLER_WEAR: "#c2410c", AIR_ENTRAINMENT: "#0891b2",
  SENSOR_DRIFT: "#64748b", SENSOR_STUCK: "#a16207", SENSOR_CALIBRATION_SHIFT: "#be185d", SENSOR_NOISE_SPIKES: "#4d7c0f",
  COMMUNICATION_LOSS: "#334155",
};
const COLORS = ["#d23434", "#1f6feb", "#b7791f", "#14894a", "#8e44ad", "#00838f"];
const START = 1440; // first minute with model output; the replay starts here
const WINDOW = 720; // minutes in the charts

const S = {
  pumps: {}, alerts: [], manuals: {}, minute: START, playing: false, selected: "PUMP-08",
  results: {}, // alert id -> {status, guide, summary, verdict, events}
  fired: new Set(), ack: new Set(), open: null, chats: {}, lastRaw: -1,
};

const fmtNum = (v, d = 1) => (v == null || Number.isNaN(v) ? "—" : Math.abs(v) >= 1000 ? Math.round(v).toString() : (+v).toFixed(d));
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const faultName = (f) => FAULT_NAME[f] || f;
const isSensor = (a) => a.event_class === "SENSOR";

function pumpTime(asset, minute) {
  const p = S.pumps[asset];
  return new Date(Date.parse(p.t0) + minute * 60000);
}
const iso = (d) => d.toISOString().replace(".000Z", "Z").replace("T", " ");

// ---------- load ----------
async function load() {
  // static package: every file was made before by build_data.py and bake.py
  const get = (f) => fetch(`data/${f}`).then((r) => r.json());
  const [guides, alerts, ...rest] = await Promise.all([
    get("guides.json"), get("alerts.json"),
    ...PUMPS.map((p) => get(`${p}.json`)), ...PUMPS.map((p) => get(`manual-${p}.json`)),
  ]);
  S.guides = guides;
  S.alerts = alerts;
  PUMPS.forEach((p, i) => { S.pumps[p] = rest[i]; S.manuals[p] = rest[i + PUMPS.length]; });
  renderAssets();
  seek(S.minute);
}

// ---------- replay ----------
let lastTs = null, acc = 0;
function frame(ts) {
  if (S.playing) {
    if (lastTs != null) acc += ((ts - lastTs) / 1000) * +$("speed").value;
    const steps = Math.floor(acc);
    if (steps > 0) {
      acc -= steps;
      advance(steps);
    }
  }
  lastTs = ts;
  requestAnimationFrame(frame);
}

function advance(steps) {
  const from = S.minute;
  const to = Math.min(from + steps, 10079);
  // stop exactly at the first new alert in (from, to]
  const next = S.alerts.find((a) => a.minute > from && a.minute <= to && !S.fired.has(a.id));
  const stopAt = next ? next.minute : to;
  S.minute = stopAt;
  for (const a of S.alerts) if (a.minute > from && a.minute <= stopAt && !S.fired.has(a.id)) fire(a, true);
  if (S.minute >= 10079) setPlaying(false);
  render();
}

function seek(m) {
  S.minute = m;
  // alerts before the cursor are in the feed, but they do not run the pipeline automatically
  for (const a of S.alerts) if (a.minute <= m) S.fired.add(a.id);
  render();
  renderFeed();
}

function setPlaying(on) {
  S.playing = on;
  $("play").textContent = on ? "❚❚ Pause" : "▶ Play";
  lastTs = null; acc = 0;
}

// ---------- alerts ----------
const keyOf = (a) => `${a.asset_id}|${a.fault_type}`;
// saved advice run of this pump and fault type (the test run with ?test=1)
const entryOf = (a) => (OPT.inject && S.guides.test[keyOf(a)]) || S.guides.guides[keyOf(a)];

function applyEvent(R, ev) {
  R.events.push(ev);
  if (ev.stage === "draft" && ev.status === "done") { R.guide = ev.guide; R.verdict = null; }
  if (ev.stage === "verify" && ev.status === "done") R.verdict = ev;
  if (ev.stage === "final") { R.final = ev; R.status = ev.status; }
  if (ev.stage === "error") { R.status = "error"; R.error = ev.message; }
}

// short text of the current step of the advice flow
function stageText(R) {
  const ev = R.events[R.events.length - 1];
  if (!ev || ev.stage === "manual") return "reading manual…";
  if (ev.stage === "draft") return ev.attempt > 1 ? "writing again…" : "writing advice…";
  if (ev.stage === "verify") return ev.status === "running" ? "checking references…" : ev.accepted ? "approved" : "wrong reference";
  if (ev.stage === "fallback") return "writing summary…";
  return "preparing advice…";
}

function updateBadge(id) {
  const b = document.querySelector(`.fi[data-id="${id}"] .badge.run`);
  const R = S.results[id];
  if (b && R) b.textContent = stageText(R);
}

// result to show for an alert; a repeat shows the advice of the original alert
const srcOf = (R) => (R?.repeatOf ? (S.results[R.repeatOf]?.final ? S.results[R.repeatOf] : R) : R);

function savedResult(events) {
  const R = { status: "running", events: [], guide: null, verdict: null };
  for (const ev of events) applyEvent(R, ev);
  return R;
}

function fire(a, live) {
  S.fired.add(a.id);
  const entry = entryOf(a);
  if (entry && entry.alert_id !== a.id) {  // repeat alert: the advice of the first alert of this pair
    S.results[a.id] = { ...savedResult(entry.events), repeatOf: entry.alert_id };
    renderFeed();
    return;
  }
  renderFeed();
  if (live && OPT.pauseOnAlert && a.asset_id === S.selected) {
    // alert of the pump on screen: stop the replay and open it until the user acknowledges it
    setPlaying(false);
    openAlert(a.id);
  } else {
    // alert of the other pump: the card goes into the list and the replay continues
    runPipeline(a.id);
  }
}

// Plays the saved events of the advice flow with short pauses, so the steps are visible.
async function runPipeline(id) {
  const a = S.alerts.find((x) => x.id === id);
  const entry = entryOf(a);
  if (!entry) { S.results[id] = { status: "error", events: [], error: "No saved advice for this alert." }; renderFeed(); return; }
  if (entry.alert_id !== id) { S.results[id] = { ...savedResult(entry.events), repeatOf: entry.alert_id }; renderFeed(); renderModal(); return; }
  const R = (S.results[id] = { status: "running", events: [], guide: null, verdict: null });
  renderFeed();
  if (S.open === id) renderModal();
  for (const ev of entry.events) {
    await sleep(ev.status === "running" ? 1100 : 350);
    applyEvent(R, ev);
    updateBadge(id);
    if (S.open === id) renderModal();
  }
  if (R.status === "running") R.status = "error";
  renderFeed(); renderAssets();
  if (S.open === id) renderModal();
}

// ---------- render: main ----------
function render() {
  const p = S.pumps[S.selected];
  if (!p) return;
  const m = S.minute;
  $("cursor").value = m;
  // day 1 = first day with model output (the first 24 h of data are the model's normalisation window)
  const day = Math.floor((m - START) / 1440) + 1, hh = String(Math.floor((m % 1440) / 60)).padStart(2, "0"), mm = String(m % 60).padStart(2, "0");
  $("clock").textContent = `Day ${day} · ${hh}:${mm}`;
  renderAssets();
  renderPump();
}

function pumpState(asset) {
  const open = S.alerts.some((a) => a.asset_id === asset && S.fired.has(a.id) && !S.ack.has(a.id) && a.minute <= S.minute && !S.results[a.id]?.repeatOf);
  if (open) return ["alert", "Alert"];
  const p = S.pumps[asset];
  const i = S.minute - p.prob_first;
  if (i >= 0) {
    const mx = Math.max(...Object.values(p.prob).map((arr) => arr[i] ?? 0));
    if (mx >= 0.9) return ["watch", "Under watch"];
  }
  const run = p.running[S.minute];
  return ["ok", run > 0.5 ? "Normal" : "Stopped"];
}

function renderAssets() {
  setHTML($("assets"), PUMPS.map((id) => {
    const p = S.pumps[id];
    if (!p) return "";
    const [cls, txt] = pumpState(id);
    return `<div class="asset ${cls} ${id === S.selected ? "sel" : ""}" data-id="${id}">
      <span class="light"></span>
      <div><div class="nm">${id}</div><div class="st">${esc(txt)}</div></div></div>`;
  }).join(""));
}

function renderPump() {
  const id = S.selected, p = S.pumps[id], m = S.minute;


  // all sensor channels of the pump, one compact row each
  const ck = p.channels.map((c) => c.key).filter((k) => p.series[k]);
  const grid = $("charts");
  if (grid.dataset.pump !== id) {
    grid.dataset.pump = id;
    grid.innerHTML = ck.map((k) => `<div class="chart"><span class="cl">${esc(p.channels.find((c) => c.key === k).label)}</span><canvas id="cc-${k}"></canvas><b id="cv-${k}"></b></div>`).join("");
  }
  const marks = S.alerts.filter((a) => a.asset_id === id && S.fired.has(a.id) && a.minute <= m).map((a) => a.minute);
  ck.forEach((k, i) => {
    const ch = p.channels.find((c) => c.key === k);
    $(`cv-${k}`).textContent = `${fmtNum(p.series[k][m], 2)} ${ch.unit}`;
    drawLine($(`cc-${k}`), [{ data: p.series[k], color: COLORS[(i + 1) % COLORS.length] }], m, { baseline: p.baseline[k], marks, axis: false });
  });

  // probabilities
  const i0 = m - p.prob_first;
  // all fault types, always in the same order
  const now = FAULT_ORDER.filter((c) => p.prob[c]).map((c) => [c, i0 >= 0 ? p.prob[c][i0] ?? 0 : 0]);
  setHTML($("prob-bars"), now.map(([c, v]) => {
    const col = v >= 0.9 ? "var(--bad)" : v >= 0.5 ? "var(--warn)" : "#9db3cc";
    return `<div class="pb ${c === "SENSOR_DRIFT" ? "grp" : ""}"><span><i class="dot" style="background:${FAULT_COLOR[c] || "#888"}"></i>${esc(faultName(c))}</span><div class="tr"><div class="fl" style="width:${(v * 100).toFixed(1)}%;background:${col}"></div><div class="th"></div></div><span class="pc">${(v * 100).toFixed(0)}%</span></div>`;
  }).join("") + (i0 < 0 ? `<div class="muted small">The model starts after 24 h of data (normalisation window).</div>` : ""));
  // lines: all fault types, always; the highest lines are drawn last (on top)
  const lo = Math.max(0, m - WINDOW);
  p.full = p.full || Object.fromEntries(Object.entries(p.prob).map(([c, arr]) => [c, new Array(p.prob_first).fill(null).concat(arr)]));
  const series = FAULT_ORDER.filter((c) => p.full[c]).map((c) => {
    let mx = 0;
    for (let t = lo; t <= m; t++) mx = Math.max(mx, p.full[c][t] ?? 0);
    return { c, data: p.full[c], mx };
  }).sort((a, b) => a.mx - b.mx);
  drawLine($("prob-chart"), series.map((s) => ({ data: s.data, color: FAULT_COLOR[s.c] || "#888", label: faultName(s.c) })), m,
    { min: 0, max: 1, threshold: 0.9, marks, legend: false });
}

function drawLine(cv, lines, m, o = {}) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const lo = Math.max(0, m - WINDOW);
  let mn = o.min, mx = o.max;
  if (mn == null || mx == null) {
    mn = Infinity; mx = -Infinity;
    for (const l of lines) for (let t = lo; t <= m; t++) { const v = l.data[t]; if (v != null) { mn = Math.min(mn, v); mx = Math.max(mx, v); } }
    if (o.baseline != null) { mn = Math.min(mn, o.baseline); mx = Math.max(mx, o.baseline); }
    if (!Number.isFinite(mn)) { mn = 0; mx = 1; }
    const pad = (mx - mn) * 0.15 || Math.abs(mx) * 0.05 || 1;
    mn -= pad; mx += pad;
  }
  const L = 4, R = w - 4, T = o.axis === false ? 2 : 4, B = h - (o.axis === false ? 2 : 14);
  const X = (t) => L + ((t - (m - WINDOW)) / WINDOW) * (R - L);
  const Y = (v) => B - ((v - mn) / (mx - mn)) * (B - T);
  g.strokeStyle = "#e7ecf2"; g.lineWidth = 1;
  g.beginPath(); g.moveTo(L, B + 0.5); g.lineTo(R, B + 0.5); g.stroke();
  g.fillStyle = "#8a96a3"; g.font = "10px Inter, system-ui";
  if (o.axis !== false) for (let k = 0; k <= 4; k++) { const t = m - WINDOW + k * 180; g.fillText(`${-12 + k * 3} h`, Math.min(X(t), R - 22), h - 2); }
  if (o.threshold != null) {
    g.strokeStyle = "#d23434"; g.setLineDash([4, 3]);
    g.beginPath(); g.moveTo(L, Y(o.threshold)); g.lineTo(R, Y(o.threshold)); g.stroke(); g.setLineDash([]);
  }
  if (o.baseline != null) {
    g.strokeStyle = "#9aa6b2"; g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(L, Y(o.baseline)); g.lineTo(R, Y(o.baseline)); g.stroke(); g.setLineDash([]);
  }
  for (const a of o.marks || []) if (a >= lo) {
    g.strokeStyle = "#d2343455"; g.lineWidth = 2; g.beginPath(); g.moveTo(X(a), T); g.lineTo(X(a), B); g.stroke();
  }
  for (const l of lines) {
    g.strokeStyle = l.color; g.lineWidth = 1.6; g.beginPath();
    let pen = false;
    for (let t = lo; t <= m; t++) {
      const v = l.data[t];
      if (v == null) { pen = false; continue; }
      if (!pen) { g.moveTo(X(t), Y(v)); pen = true; } else g.lineTo(X(t), Y(v));
    }
    g.stroke();
  }
  if (o.legend) {
    let x = L + 4;
    g.font = "11px Inter, system-ui";
    for (const l of lines) {
      g.fillStyle = l.color; g.fillRect(x, T + 2, 9, 9);
      g.fillStyle = "#3b4652"; g.fillText(l.label, x + 13, T + 10);
      x += g.measureText(l.label).width + 26;
    }
  }
}


// ---------- feed ----------
function renderFeed() {
  const items = S.alerts.filter((a) => S.fired.has(a.id) && a.minute <= S.minute).reverse();
  const open = items.filter((a) => !S.ack.has(a.id) && !S.results[a.id]?.repeatOf).length;
  $("alert-count").textContent = open || "";
  $("alert-count").hidden = !open;
  if (!items.length) {
    $("feed").innerHTML = `<div class="empty"><div><div class="big">✓ No alerts</div><div>The fault model watches both pumps.</div></div></div>`;
    return;
  }
  const feed = $("feed"), keep = feed.scrollTop;
  const anchorId = S.open || feed.querySelector(".fi")?.dataset.id;
  const anchorTop = anchorId ? feed.querySelector(`.fi[data-id="${anchorId}"]`)?.getBoundingClientRect().top : null;
  $("detail-home").appendChild($("detail")); // keep the detail block when the cards are drawn again
  feed.innerHTML = items.map((a) => {
    const R = S.results[a.id];
    const src = srcOf(R);
    let badge = "";
    if (R?.repeatOf) badge = `<span class="badge">repeat</span>`;
    else if (R?.status === "running") badge = `<span class="badge run">${esc(stageText(R))}</span>`;
    else if (R?.status === "accepted") badge = `<span class="badge blank"></span>`; // keeps the card height
    else if (R?.status === "fallback") badge = `<span class="badge fb">summary only</span>`;
    else if (R?.status === "error") badge = `<span class="badge fb">LLM error</span>`;
    const t = iso(new Date(a.time)).slice(5, 16);
    const sum = src?.final?.status === "accepted" ? src.guide.summary : src?.final?.summary;
    const open = a.id === S.open;
    return `<div class="fi ${isSensor(a) ? "sensor" : ""} ${open ? "open" : ""} ${!open && (S.ack.has(a.id) || R?.repeatOf) ? "ack" : ""}" data-id="${a.id}">
      <div class="r1"><b>${a.asset_id}</b> · ${t} UTC</div>
      <div class="r2">${esc(faultName(a.fault_type))}${isSensor(a) ? ' <span class="muted small">sensor fault</span>' : ""}</div>
      ${sum && !R?.repeatOf && !open ? `<div class="sm">${esc(sum)}</div>` : ""}
      <span class="chev" aria-hidden="true">›</span>
      <div class="side"><div class="pr">${(a.confidence * 100).toFixed(0)} %<small>probability</small></div>${badge}</div>
      ${open ? `<div class="slot"></div>` : ""}</div>`;
  }).join("");
  const slot = document.querySelector(".fi.open .slot");
  if (slot) slot.appendChild($("detail"));
  feed.scrollTop = keep;
  const anchor = anchorId && feed.querySelector(`.fi[data-id="${anchorId}"]`);
  if (anchor && anchorTop != null && (S.open || keep > 0)) feed.scrollTop += anchor.getBoundingClientRect().top - anchorTop;
}

// ---------- alert detail ----------
function openAlert(id) {
  if (S.open && S.open !== id) S.ack.add(S.open);
  S.open = id;
  const a = S.alerts.find((x) => x.id === id);
  S.selected = a.asset_id;
  $("clause").hidden = true;
  if (!S.results[id]) runPipeline(id);
  renderFeed();
  renderModal();
  renderChat();
  render();
  const card = document.querySelector(".fi.open");
  if (card) $("feed").scrollTo({ top: card.offsetTop - $("feed").offsetTop - 4, behavior: "smooth" });
}

function closeModal() {
  if (S.open) S.ack.add(S.open);
  S.open = null;
  renderFeed(); render();
}

function cite(asset, cid, ok = true) {
  const known = !!clauseText(asset, cid);
  return `<span class="cite ${known && ok ? "" : "badc"}" data-c="${esc(cid)}" title="${known ? "Show manual clause" : "Not in the manual"}">§${esc(cid)}</span>`;
}

function clauseText(asset, cid) {
  const man = S.manuals[asset];
  const sec = man.sections.find((s) => String(s.num) === cid.split(".")[0]);
  const c = sec && sec.clauses.find((x) => x.id === cid);
  return c ? { sec, text: c.text } : null;
}

function showClause(asset, cid) {
  const c = clauseText(asset, cid);
  const box = $("clause");
  box.hidden = false;
  document.querySelectorAll(".cite.on").forEach((e) => e.classList.remove("on"));
  document.querySelectorAll(`.cite[data-c="${CSS.escape(cid)}"]`).forEach((e) => e.classList.add("on"));
  box.innerHTML = c
    ? `<div class="cl-h">Manual §${esc(cid)} · ${esc(c.sec.title)}</div>${esc(c.text)}`
    : `<div class="cl-h">§${esc(cid)}</div>This clause number is not in the manual.`;
}

function renderModal() {
  const id = S.open;
  if (!id) return;
  const a = S.alerts.find((x) => x.id === id);
  const p = S.pumps[a.asset_id];
  const R = S.results[id] || { events: [] };
  const src = srcOf(R);

  $("m-evidence").textContent = SIGNAL_NAME[a.evidence_signal] || a.evidence_signal || "—";

  // values
  if ($("m-values")) $("m-values").innerHTML = `<tr><th>Signal</th><th class="n">Now</th><th class="n">Baseline</th><th class="n">Δ</th></tr>` +
    a.values.map((v) => `<tr class="${v.delta_pct != null && Math.abs(v.delta_pct) > 10 ? "hi" : ""}"><td>${esc(v.label)}</td>
      <td class="n">${fmtNum(v.now, 2)} ${esc(v.unit)}</td><td class="n">${fmtNum(v.baseline, 2)}</td>
      <td class="n">${v.delta_pct == null ? "—" : (v.delta_pct > 0 ? "+" : "") + v.delta_pct.toFixed(1) + "%"}</td></tr>`).join("");

  // steps
  const steps = [];
  steps.push({ cls: "done", ic: "✓", tt: "Alert from the fault model", ds: "" });
  const evs = src.events || [];
  for (const ev of evs) {
    if (ev.stage === "manual") {
      steps.push({ cls: "done", ic: "✓", tt: "Pump manual sections found", ds: "",
        extra: `<div class="secchips">${ev.sections.map((s) => `<span class="sc">§${s.num} ${esc(s.title)}</span>`).join("")}</div>` });
    } else if (ev.stage === "draft") {
      const run = ev.status === "running";
      if (!run) steps.pop();
      steps.push({ cls: run ? "run" : "done", ic: run ? "" : "✓", tt: `Write advice with manual references${ev.attempt > 1 ? " · try " + ev.attempt : ""}`,
        ds: run ? "writing…" : "", extra: ev.test_note ? `<div class="note">${esc(ev.test_note)}</div>` : "" });
    } else if (ev.stage === "verify") {
      const run = ev.status === "running";
      if (!run) steps.pop();
      if (run) steps.push({ cls: "run", ic: "", tt: "Check the references against the manual", ds: "checking…" });
      else {
        const ok = ev.checks.filter((c) => c.supported).length;
        const bad = ev.checks.filter((c) => !c.supported);
        steps.push({ cls: ev.accepted ? "done" : "fail", ic: ev.accepted ? "✓" : "✗",
          tt: ev.accepted ? "References correct" : "Wrong reference found · write again",
          ds: `${ok} of ${ev.checks.length} steps match the manual`,
          extra: bad.length ? `<ul class="rej">${bad.map((c) => `<li><b>${c.id}</b> ${esc(c.reason)}</li>`).join("")}${ev.code_issues.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "" });
      }
    } else if (ev.stage === "fallback") {
      steps.push({ cls: "run", ic: "", tt: "Not approved twice · summary only", ds: "" });
    } else if (ev.stage === "final") {
      if (ev.status === "fallback") steps.pop();
      steps.push(ev.status === "accepted"
        ? { cls: "done", ic: "✓", tt: "Advice approved", ds: `${ev.seconds} s` }
        : { cls: "warn", ic: "!", tt: "Advice not approved · summary only", ds: `${ev.seconds} s` });
    } else if (ev.stage === "error") {
      steps.push({ cls: "fail", ic: "✗", tt: "Language model error", ds: esc(ev.message) });
    }
  }
  if (!evs.length && src.status === "running") steps.push({ cls: "run", ic: "", tt: "Starting…", ds: "" });
  if ($("steps")) $("steps").innerHTML = steps.map((s) => `<li class="step ${s.cls}"><span class="ic">${s.ic}</span><div><div class="tt">${s.tt}</div><div class="ds">${s.ds}</div>${s.extra || ""}</div></li>`).join("");

  // guide
  const orig = R.repeatOf && S.alerts.find((x) => x.id === R.repeatOf);
  const note = orig ? `<div class="g-repeat">Same fault as the alert of ${iso(new Date(orig.time)).slice(5, 16)} UTC. The advice is from that alert.</div>` : "";
  setHTML($("guide"), note + renderGuide(a, src));
  $("guide").classList.toggle("g-draft", !!src.guide && src.status === "running");
  $("chat-qs").classList.toggle("wait", src.status === "running");
}

function meta(m) {
  if (!m) return "";
  return m.cached ? "cached reply" : `${(m.ms / 1000).toFixed(1)} s${m.tokens ? ` · ${m.tokens} tokens` : ""}`;
}

function renderGuide(a, R) {
  const asset = a.asset_id;
  if (R.status === "error") return `<div class="g-banner bad">The language model is not available. ${esc(R.error || "")}</div>${fallbackBlock(a, null)}`;
  if (R.final?.status === "fallback") return `<div class="g-banner fb">⚠ Advice could not be checked · summary only</div>${fallbackBlock(a, R.final)}`;
  if (!R.guide) return `<div class="g-skel"><i style="width:92%"></i><i style="width:70%"></i>${"<i></i>".repeat(5)}<i style="width:80%"></i></div>`;
  const g = R.guide, v = R.verdict;
  const checks = v ? v.checks : null;
  const okc = (i) => !checks || !checks[i] || checks[i].supported;
  const n = g.actions.length;
  return `<div class="g-body">
    <p class="g-sum">${esc(g.summary)}</p>
    <ol class="g-actions">${g.actions.map((x, i) => `<li class="${okc(i) ? "" : "no"}"><span>${esc(x.text)}${x.citations.map((c) => cite(asset, c, okc(i))).join("")}</span></li>`).join("")}</ol>
    <div class="g-esc"><span><b>Escalate if:</b> ${esc(g.escalate_if.text)}${g.escalate_if.citations.map((c) => cite(asset, c, okc(n))).join("")}</span></div></div>`;
}

function fallbackBlock(a, fin) {
  const secs = (fin?.sections || []).map((s) => `<span class="sc">§${s.num} ${esc(s.title)}</span>`).join(" ");
  return `${fin?.summary ? `<p class="g-fb-sum">${esc(fin.summary)}</p>` : ""}
    <p class="muted">See the pump manual${secs ? ":" : "."}</p><div class="secchips">${secs}</div>`;
}

// ---------- prepared questions ----------
function renderChat() {
  const id = S.open;
  if (!id) return;
  const a = S.alerts.find((x) => x.id === id);
  const log = S.chats[id] || [];
  const asked = new Set(log.filter((m) => m.role === "user").map((m) => m.content));
  const qs = (S.guides.questions[keyOf(a)] || []).filter((x) => !asked.has(x.q));
  $("chat-log").innerHTML = log.map((m) => `<div class="msg ${m.role === "user" ? "u" : "a"} ${m.typing ? "typing" : ""}">${m.role === "user" ? esc(m.content) : withCites(a.asset_id, m.content)}</div>`).join("");
  setHTML($("chat-qs"), qs.map((x) => `<button class="qchip" data-q="${esc(x.q)}">${esc(x.q)}</button>`).join(""));
  $("chat-log").scrollTop = 1e9;
}

function withCites(asset, text) {
  return esc(text).replace(/\[(?:§\s*)?(\d{1,2}\.\d{1,2})\]/g, (_, c) => cite(asset, c));
}

// Shows the saved answer of a prepared question, word by word.
async function ask(q) {
  const id = S.open;
  const a = S.alerts.find((x) => x.id === id);
  const item = (S.guides.questions[keyOf(a)] || []).find((x) => x.q === q);
  if (!item) return;
  const log = (S.chats[id] = S.chats[id] || []);
  log.push({ role: "user", content: q });
  const ans = { role: "assistant", content: "", typing: true };
  log.push(ans);
  renderChat();
  await sleep(500);
  const words = item.a.split(/(\s+)/);
  for (let i = 0; i < words.length; i += 2) {
    ans.content = words.slice(0, i + 2).join("");
    if (S.open === id) renderChat();
    await sleep(25);
  }
  ans.content = item.a;
  ans.typing = false;
  if (S.open === id) renderChat();
}

// ---------- events ----------
$("play").onclick = () => setPlaying(!S.playing);
$("cursor").oninput = (e) => { setPlaying(false); seek(Math.max(START, +e.target.value)); };
$("assets").onpointerdown = (e) => { const el = e.target.closest(".asset"); if (el) { S.selected = el.dataset.id; render(); } };
$("feed").onclick = (e) => {
  if (e.target.closest("#detail")) {
    const c = e.target.closest(".cite");
    if (c && S.open) showClause(S.alerts.find((x) => x.id === S.open).asset_id, c.dataset.c);
    return;
  }
  const el = e.target.closest(".fi");
  if (!el) return;
  setPlaying(false);
  if (el.dataset.id === S.open) closeModal(); else openAlert(el.dataset.id);
};
// Acknowledge: collapse the alert and continue the replay
$("m-close").onclick = () => { closeModal(); if (S.minute < 10079) setPlaying(true); };
$("chat-qs").onclick = (e) => { const b = e.target.closest(".qchip"); if (b && !$("chat-qs").classList.contains("wait")) ask(b.dataset.q); };
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" && e.target.type === "text") return;
  if (e.key === " ") { e.preventDefault(); setPlaying(!S.playing); }
  if (e.key === "Escape" && S.open) closeModal();
});
window.addEventListener("resize", () => render());

load().then(() => requestAnimationFrame(frame));
