// Therapist view: patient picker, live rep table, charts across sessions, session note.
// Charts are hand-drawn inline SVG (built as HTML text, so no namespace address is needed).
import { connectLive, api, simBanner, modeClass } from "./common.js";

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = x => typeof x === "number" && Number.isFinite(x);
const fx = (x, d = 1) => (num(x) ? x.toFixed(d).replace("-", "−") : "–");
const signed = x => (num(x) ? (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(2) : "–");
const STATE_MS = 1500;

// Plain-English explanations, one per metric. Shown from the ⓘ buttons.
const TIPS = {
  rep: "Repetition number within the session (for a strength test: the try).",
  exercise: "The programme the arm ran: forward reach (assisted), push or row (resisted), or the push strength test.",
  mode: "assist: the arm helps the movement. transparent: the arm moves freely. resist: the arm pushes back. isometric: a strength-test try with the handle held still.",
  dial: "The help/challenge setting. +1: the arm does the work. 0: free movement. −1: maximum resistance. A dial that falls over time means less help was needed.",
  range: "How far the handle travelled along the line in this rep, in centimetres. The full path is about 30 cm.",
  path: "How far the hand wandered off the straight line on average, in centimetres. Lower is straighter.",
  smooth: "SPARC smoothness (Balasubramanian et al., 2015). It has no unit and is always negative; closer to zero is smoother.",
  peak: "The highest force the patient put on the handle, in newtons. A device reading, not a validated strength score. Strength test readings are capped at about 30 N by the robot's safety limit.",
  contrib: "Contribution: the share of the movement done by the patient rather than by the arm. A team-defined index, not clinically validated. Shown for the assisted reach only.",
  result: "completed: the handle reached the end of the path. not completed: it stopped short. rescued: the arm stepped in after the patient stalled.",
};

const COLS = [
  { k: "rep", label: "Rep", left: true },
  { k: "exercise", label: "Exercise", left: true },
  { k: "mode", label: "Mode", left: true },
  { k: "dial", label: "Dial" },
  { k: "range", label: "Range", unit: "cm" },
  { k: "path", label: "Path error", unit: "cm" },
  { k: "smooth", label: "Smoothness" },
  { k: "peak", label: "Peak", unit: "N" },
  { k: "contrib", label: "Contribution", unit: "%" },
  { k: "result", label: "Result", left: true },
];

// One small chart per metric. `get` reads a session row; `on` says which exercises it means something for.
const METRICS = [
  { k: "dial", title: "Mean dial", unit: "dial (−1 resist … +1 assist)", d: 2, on: ex => ex !== "armtest",
    get: s => s.mean_dial, domain: () => [-1, 1], zero: true, say: v => signed(v) },
  { k: "contrib", title: "Contribution", unit: "% of the movement", d: 0, on: ex => ex === "reach",
    get: s => (num(s.mean_contribution) ? s.mean_contribution * 100 : null), domain: () => [0, 100], say: v => `${fx(v, 0)} %` },
  { k: "peak", title: "Peak force", unit: "N", d: 1, on: () => true,
    get: (s, ex) => (ex === "armtest" ? s.best_peak_force_n : s.mean_peak_force_n),
    domain: vs => [0, niceCeil(Math.max(...vs))], say: v => `${fx(v, 1)} N` },
  { k: "path", title: "Path error", unit: "cm", d: 1, on: ex => ex !== "armtest",
    get: s => (num(s.mean_path_err_mean_m) ? s.mean_path_err_mean_m * 100 : null),
    domain: vs => [0, niceCeil(Math.max(...vs))], say: v => `${fx(v, 1)} cm` },
  { k: "smooth", title: "Smoothness", unit: "SPARC (no unit; nearer 0 = smoother)", d: 2, on: ex => ex !== "armtest",
    get: s => s.mean_sparc,
    domain: vs => { const lo = Math.floor(Math.min(...vs) * 2) / 2, hi = Math.ceil(Math.max(...vs) * 2) / 2; return [lo, hi > lo ? hi : lo + 0.5]; },
    say: v => fx(v, 2) },
];

const S = {
  patients: [], patientId: null,
  sessions: [], sessionId: null,          // sessions of the selected patient, oldest first
  live: null,                             // {session_id, patient_id, simulated, exercise} while a session runs
  liveSample: null,
  reps: new Map(),                        // session_id -> reps, by idx
  newRep: null,                           // "sid:idx" of the row to flash
  exNames: { reach: "Forward reach", push: "Push", pull: "Row", armtest: "Push strength test" },
  histEx: null,
  note: { sid: null, text: "" },
  hover: null,                            // session id under the pointer on a chart
  seq: 0,
};

// ---------------------------------------------------------------- helpers
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function day(iso) {
  const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(iso || "");
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}` : "?";
}
function dayTime(iso) {
  const m = /T(\d\d:\d\d)/.exec(iso || "");
  return `${day(iso)}${m ? ` ${m[1]}` : ""}`;
}
const exName = id => S.exNames[id] || id || "–";
const sessionById = id => S.sessions.find(s => s.session_id === id);
const isLive = id => !!S.live && S.live.session_id === id;
function niceCeil(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (v <= m * p * 1.0001) return m * p;
  return 10 * p;
}
function status(text) { $("status").textContent = text || ""; }
async function get(path) {
  try { const r = await api.get(path); status(""); return r; }
  catch (e) { status(e.status ? `${path}: ${e.message} (${e.status})` : "No answer from the server."); throw e; }
}

// ---------------------------------------------------------------- data
async function loadPatients() {
  S.patients = await get("/api/patients");
  const sel = $("patient");
  sel.textContent = "";
  if (!S.patients.length) sel.append(new Option("No patients recorded yet", ""));
  for (const p of S.patients) sel.append(new Option(`${p.display_name} · ${p.n_sessions} session${p.n_sessions === 1 ? "" : "s"}`, p.id));
  if (S.patientId) sel.value = S.patientId;
}

async function loadSessions() {
  if (!S.patientId) { S.sessions = []; return; }
  const rows = await get(`/api/patients/${encodeURIComponent(S.patientId)}/sessions`);
  S.sessions = rows.slice().sort((a, b) => (a.started_at + a.session_id < b.started_at + b.session_id ? -1 : 1));
}

function fillSessions() {
  const sel = $("session");
  sel.textContent = "";
  if (!S.sessions.length) sel.append(new Option("No sessions", ""));
  for (const s of S.sessions.slice().reverse()) {
    const n = isLive(s.session_id) ? (S.reps.get(s.session_id) || []).length : s.n_reps;
    sel.append(new Option(`${dayTime(s.started_at)} · ${exName(s.exercise)} · ${n} rep${n === 1 ? "" : "s"}${isLive(s.session_id) ? " · LIVE" : ""}`, s.session_id));
  }
  if (S.sessionId) sel.value = S.sessionId;
}

async function selectPatient(id, wantSession) {
  const mine = ++S.seq;
  S.patientId = id || null;
  if ($("patient").value !== (id || "")) $("patient").value = id || "";
  try { await loadSessions(); } catch { S.sessions = []; }
  if (mine !== S.seq) return;
  const pick = (wantSession && sessionById(wantSession)) || (S.live && sessionById(S.live.session_id))
    || S.sessions[S.sessions.length - 1] || null;
  await selectSession(pick ? pick.session_id : null);
}

async function selectSession(id) {
  S.sessionId = id || null;
  const s = sessionById(id);
  if (s) S.histEx = s.exercise;
  fillSessions();
  renderAll();
  if (!id) return;
  if (!isLive(id)) {
    try {
      const reps = await get(`/api/sessions/${encodeURIComponent(id)}/reps`);
      S.reps.set(id, reps);
    } catch {}
    if (S.sessionId === id) renderReps();
  }
  loadNote();
}

function mergeRep(r) {
  const list = S.reps.get(r.session_id) || [];
  const i = list.findIndex(x => x.idx === r.idx);
  if (i >= 0) list[i] = r; else list.push(r);
  list.sort((a, b) => a.idx - b.idx);
  S.reps.set(r.session_id, list);
}

async function loadNote() {
  const id = S.sessionId;
  if (!id) return;
  if (isLive(id)) { S.note = { sid: id, text: "" }; renderNote(); return; }
  try {
    const text = await get(`/api/sessions/${encodeURIComponent(id)}/note`);
    if (S.sessionId === id) { S.note = { sid: id, text: String(text) }; renderNote(); }
  } catch {
    if (S.sessionId === id) { S.note = { sid: id, text: "" }; renderNote(); }
  }
}

// ---------------------------------------------------------------- live session tracking
let pollBusy = false, lastAsk = 0;
async function pollState() {
  if (pollBusy) return;
  pollBusy = true;
  lastAsk = performance.now();
  try {
    const st = await api.get("/api/state");
    const sess = st && st.session;
    if (sess && (!S.live || S.live.session_id !== sess.session_id)) await liveStarted(sess);
    else if (!sess && S.live) await liveEnded();
  } catch {} finally { pollBusy = false; }
}
function askSoon() { if (performance.now() - lastAsk > 400) pollState(); }

async function liveStarted(sess) {
  S.live = { ...sess };
  S.liveSample = null;
  if (!S.reps.has(sess.session_id)) S.reps.set(sess.session_id, []);
  try {                                    // reps that happened before this page was opened
    for (const r of await api.get(`/api/sessions/${encodeURIComponent(sess.session_id)}/reps`)) mergeRep({ ...r, session_id: sess.session_id });
  } catch {}
  try { await loadPatients(); } catch {}
  await selectPatient(sess.patient_id, sess.session_id);
}

async function liveEnded() {
  const done = S.live;
  S.live = null;
  S.liveSample = null;
  try { await loadPatients(); } catch {}
  await selectPatient(done.patient_id, done.session_id);    // shows the just-finished session and its note
}

let refreshTimer = null;
function refreshSessionsSoon() {           // keep the charts' newest point in step with the live reps
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    if (!S.live || S.live.patient_id !== S.patientId) return;
    try { await loadSessions(); } catch { return; }
    fillSessions();
    renderCharts();
  }, 300);
}

function onRep(r) {
  mergeRep(r);
  S.newRep = `${r.session_id}:${r.idx}`;
  if (!isLive(r.session_id)) askSoon();
  if (r.session_id === S.sessionId) { renderReps(); fillSessions(); }
  refreshSessionsSoon();
}

function onSample(m) {
  if (!S.live) askSoon();
  S.liveSample = m;
  renderLiveLine();
}

// ---------------------------------------------------------------- rendering: reps
function buildHead() {
  const tr = $("repsHead");
  for (const c of COLS) {
    const th = document.createElement("th");
    if (c.left) th.className = "l";
    th.append(c.label);
    if (c.unit) { const u = document.createElement("span"); u.className = "unit"; u.textContent = ` (${c.unit})`; th.append(u); }
    th.append(tipButton(c.k, c.label));
    tr.append(th);
  }
}

function tipButton(key, label) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "tip"; b.textContent = "i";
  b.dataset.tip = key;
  b.title = TIPS[key];
  b.setAttribute("aria-label", `What ${label} means`);
  b.setAttribute("aria-expanded", "false");
  return b;
}

function repCells(r, sessionEx) {
  const ex = r.exercise || sessionEx;
  const iso = r.mode === "isometric";
  const td = (text, left) => { const c = document.createElement("td"); if (left) c.className = "l"; c.textContent = text; return c; };
  const mode = td("", true);
  const span = document.createElement("span");
  span.className = `mode-${modeClass(r.mode)}`;
  span.textContent = r.mode || "–";
  mode.append(span);
  const res = td("", true);
  const ok = document.createElement("span");
  ok.textContent = r.completed ? "completed" : "not completed";
  if (!r.completed) ok.className = "no";
  res.append(ok);
  if (r.rescued) { const chip = document.createElement("span"); chip.className = "chip"; chip.textContent = "rescued"; res.append(chip); }
  return [
    td(String(r.idx + 1), true),
    td(exName(ex), true),
    mode,
    td(iso ? "–" : signed(r.dial)),
    td(iso ? "–" : fx(r.rom_m * 100, 1)),
    td(iso ? "–" : fx(r.path_err_mean_m * 100, 1)),
    td(iso ? "–" : fx(r.sparc, 2)),
    td(fx(r.peak_force_n, 1)),
    td(ex === "reach" && !iso ? fx(r.contribution * 100, 0) : "–"),
    res,
  ];
}

function renderReps() {
  const id = S.sessionId, s = sessionById(id), live = isLive(id);
  const reps = (id && S.reps.get(id)) || [];
  $("repsTitle").textContent = live ? "Live session" : "Session reps";
  $("liveTag").hidden = !live;
  const sim = reps.length ? reps.some(r => r.simulated) : s ? s.simulated : live ? S.live.simulated : undefined;
  simBanner($("repsBadge"), id ? sim : undefined);
  const body = $("repsBody");
  body.textContent = "";
  for (const r of reps.slice().reverse()) {           // newest first
    const tr = document.createElement("tr");
    if (S.newRep === `${id}:${r.idx}`) tr.className = "new";
    tr.append(...repCells(r, s && s.exercise));
    body.append(tr);
  }
  $("repsEmpty").hidden = reps.length > 0;
  $("repsEmpty").textContent = !id ? "No session selected." : live ? "Waiting for the first rep." : "No reps recorded in this session.";
  $("capNote").hidden = !reps.some(r => r.mode === "isometric");
  renderLiveLine();
}

function renderLiveLine() {
  const id = S.sessionId, s = sessionById(id);
  if (!id) { $("repsSub").textContent = ""; return; }
  const n = (S.reps.get(id) || []).length;
  const bits = [s ? exName(s.exercise) : "", s ? `started ${dayTime(s.started_at)}` : ""];
  const m = S.liveSample;
  if (isLive(id) && m) {
    bits.push(`rep ${m.rep_count ?? n} of ${m.reps_target ?? "∞"}`, `phase ${m.phase}`, `dial ${signed(m.dial)}`);
    if (m.arm_mode === "hold" || m.arm_mode === "fault") bits.push("ARM STOPPED");
    else if (m.done) bits.push("set finished, waiting for the operator to stop");
  } else {
    bits.push(`${n} rep${n === 1 ? "" : "s"}`);
  }
  $("repsSub").textContent = bits.filter(Boolean).join(" · ");
}

// ---------------------------------------------------------------- rendering: charts
const W = 320, H = 184, L = 38, R = 12, T = 26, B = 34;

function chartSvg(def, pts, lo, hi, selId) {
  const pw = W - L - R, ph = H - T - B;
  const X = i => (pts.length === 1 ? L + pw / 2 : L + (i * pw) / (pts.length - 1));
  const Y = v => T + ph - ((v - lo) / (hi - lo)) * ph;
  const tick = v => String(+v.toFixed(2)).replace("-", "−");
  let g = "";
  for (const v of [lo, (lo + hi) / 2, hi]) {
    g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/>`
       + `<text class="axis" x="${L - 5}" y="${(Y(v) + 3.5).toFixed(1)}" text-anchor="end">${tick(v)}</text>`;
  }
  if (def.zero && lo < 0 && hi > 0) g += `<line class="zero" x1="${L}" x2="${W - R}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}"/>`;
  const ticksAt = [...new Set([0, Math.floor((pts.length - 1) / 2), pts.length - 1])];
  ticksAt.forEach((i, n) => {
    const anchor = pts.length === 1 ? "middle" : n === 0 ? "start" : i === pts.length - 1 ? "end" : "middle";
    g += `<text class="axis" x="${X(i).toFixed(1)}" y="${H - B + 14}" text-anchor="${anchor}">${esc(day(pts[i].s.started_at))}</text>`;
  });
  g += `<text class="axis" x="${L + pw / 2}" y="${H - 4}" text-anchor="middle">session date (${pts.length} session${pts.length === 1 ? "" : "s"})</text>`;
  g += `<text class="unit" x="2" y="12">${esc(def.unit)}</text>`;
  const nSim = pts.filter(p => p.s.simulated).length;
  if (nSim) {                              // the label sits ON the chart, so a screenshot of it still says so
    const label = nSim === pts.length ? "SIMULATED" : "PARTLY SIMULATED", w = label.length * 7 + 12;
    g += `<g class="simtag"><rect x="${W - R - w}" y="2" width="${w}" height="16" rx="3"/>`
       + `<text x="${W - R - w / 2}" y="13.5" text-anchor="middle">${label}</text></g>`;
  }
  g += `<line class="guide" data-guide x1="0" x2="0" y1="${T}" y2="${T + ph}" visibility="hidden"/>`;
  if (pts.length > 1) g += `<polyline class="line" points="${pts.map((p, i) => `${X(i).toFixed(1)},${Y(p.v).toFixed(1)}`).join(" ")}"/>`;
  pts.forEach((p, i) => {
    const sel = p.s.session_id === selId;
    g += `<circle class="pt${sel ? " sel" : ""}" cx="${X(i).toFixed(1)}" cy="${Y(p.v).toFixed(1)}" r="${sel ? 5.5 : 4}"/>`;
  });
  const slot = pts.length === 1 ? pw : pw / (pts.length - 1);
  pts.forEach((p, i) => {                  // hit areas wider than the marks
    g += `<rect class="hit" data-sid="${esc(p.s.session_id)}" data-x="${X(i).toFixed(1)}" x="${(X(i) - slot / 2).toFixed(1)}" y="${T}" width="${slot.toFixed(1)}" height="${ph + 16}"/>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(def.title)} across sessions${nSim ? ", simulated data" : ""}">${g}</svg>`;
}

function readText(def, pts, sid) {
  const p = pts.find(x => x.s.session_id === sid) || pts[pts.length - 1];
  if (!p) return "";
  return `<b>${esc(def.say(p.v))}</b> · ${esc(dayTime(p.s.started_at))}${p.s.simulated ? " · SIMULATED" : ""}`;
}

let chartData = {};                        // metric key -> {def, pts}
function renderCharts() {
  const exs = [...new Set(S.sessions.map(s => s.exercise))];
  if (!exs.includes(S.histEx)) S.histEx = exs[exs.length - 1] || null;
  const sel = $("histEx");
  sel.textContent = "";
  for (const e of exs) sel.append(new Option(exName(e), e));
  if (S.histEx) sel.value = S.histEx;
  sel.disabled = exs.length < 2;

  const ex = S.histEx, rows = S.sessions.filter(s => s.exercise === ex);
  const p = S.patients.find(x => x.id === S.patientId);
  $("histSub").textContent = !S.patientId ? "" : !rows.length ? "No sessions for this patient yet."
    : `${p ? p.display_name : S.patientId}: one point per ${exName(ex)} session (the mean over its reps). Tap a point to open that session.`;
  const box = $("charts");
  box.textContent = "";
  chartData = {};
  if (!rows.length) return;
  for (const def of METRICS) {
    const card = document.createElement("div");
    card.className = "chart";
    card.dataset.k = def.k;
    const h = document.createElement("h3");
    h.textContent = def.k === "peak" && ex === "armtest" ? "Best peak force" : def.title;
    h.append(tipButton(def.k, def.title));
    card.append(h);
    const body = document.createElement("div");
    const pts = def.on(ex) ? rows.map(s => ({ s, v: def.get(s, ex) })).filter(x => num(x.v)) : [];
    if (!def.on(ex)) body.innerHTML = `<div class="na">Not measured for ${esc(exName(ex).toLowerCase())}.</div>`;
    else if (!pts.length) body.innerHTML = `<div class="na">No reps recorded yet.</div>`;
    else {
      const [lo, hi] = def.domain(pts.map(x => x.v));
      chartData[def.k] = { def, pts };
      body.innerHTML = chartSvg(def, pts, lo, hi, S.sessionId) + `<div class="read">${readText(def, pts, S.sessionId)}</div>`;
    }
    card.append(body);
    box.append(card);
  }
}

function hoverCharts(sid) {
  if (S.hover === sid) return;
  S.hover = sid;
  for (const card of $("charts").children) {
    const d = chartData[card.dataset.k];
    if (!d) continue;
    const guide = card.querySelector("[data-guide]"), read = card.querySelector(".read");
    const hit = sid && [...card.querySelectorAll(".hit")].find(h => h.dataset.sid === sid);
    if (hit) {
      guide.setAttribute("x1", hit.dataset.x); guide.setAttribute("x2", hit.dataset.x);
      guide.setAttribute("visibility", "visible");
    } else guide.setAttribute("visibility", "hidden");
    read.innerHTML = readText(d.def, d.pts, hit ? sid : S.sessionId);
  }
}

// ---------------------------------------------------------------- rendering: note, header
function renderNote() {
  const id = S.sessionId, s = sessionById(id), live = isLive(id);
  const has = !!S.note.text && S.note.sid === id;
  $("noteSub").textContent = !id ? "No session selected."
    : live ? "The note is written when the operator stops this session."
    : `${s ? `${dayTime(s.started_at)} · ${exName(s.exercise)}` : id}. Drafted automatically from device data, for the therapist to review.`;
  $("note").textContent = has ? S.note.text : "";
  $("note").hidden = !has;
  $("copy").disabled = !has;
  $("copyMsg").textContent = "";
}

function renderAll() {
  const p = S.patients.find(x => x.id === S.patientId);
  simBanner($("pBadge"), p ? p.simulated : undefined);
  renderReps();
  renderCharts();
  renderNote();
}

// ---------------------------------------------------------------- copy, tips
async function copyNote() {
  const text = S.note.text;
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch {}
  if (!ok) {                               // plain http on a phone has no clipboard API: use a selection instead
    const ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;";
    document.body.append(ta);
    ta.select(); ta.setSelectionRange(0, text.length);
    try { ok = document.execCommand("copy"); } catch {}
    ta.remove();
  }
  $("copyMsg").textContent = ok ? "Copied." : "Could not copy here: press and hold the note to select it.";
}

function closeTip() {
  $("tipbox").hidden = true;
  for (const b of document.querySelectorAll('.tip[aria-expanded="true"]')) b.setAttribute("aria-expanded", "false");
}
function openTip(btn) {
  const box = $("tipbox");
  box.textContent = TIPS[btn.dataset.tip] || "";
  box.hidden = false;
  btn.setAttribute("aria-expanded", "true");
  const r = btn.getBoundingClientRect(), vw = document.documentElement.clientWidth;
  const left = Math.max(8, Math.min(r.left + r.width / 2 - box.offsetWidth / 2, vw - box.offsetWidth - 8));
  box.style.left = `${left + window.scrollX}px`;
  box.style.top = `${r.bottom + 8 + window.scrollY}px`;
}

// ---------------------------------------------------------------- wiring
buildHead();
$("patient").onchange = () => selectPatient($("patient").value);
$("session").onchange = () => selectSession($("session").value);
$("histEx").onchange = () => { S.histEx = $("histEx").value; renderCharts(); };
$("copy").onclick = copyNote;

document.addEventListener("click", e => {
  const btn = e.target.closest && e.target.closest(".tip");
  if (btn) {
    const wasOpen = btn.getAttribute("aria-expanded") === "true";
    closeTip();
    if (!wasOpen) openTip(btn);
    return;
  }
  closeTip();
  const hit = e.target.closest && e.target.closest(".hit");
  if (hit && hit.dataset.sid !== S.sessionId) { S.hover = null; selectSession(hit.dataset.sid); }
});
document.addEventListener("keydown", e => { if (e.key === "Escape") closeTip(); });
window.addEventListener("resize", closeTip);
$("charts").addEventListener("pointerover", e => {
  const hit = e.target.closest && e.target.closest(".hit");
  if (hit) hoverCharts(hit.dataset.sid);
});
$("charts").addEventListener("pointerleave", () => hoverCharts(null));

connectLive(onSample, onRep, s => {
  $("dot").className = `dot ${s}`;
  $("conn").textContent = s === "live" ? "connected" : s;
});

(async function init() {
  const q = new URLSearchParams(location.search);
  api.get("/api/exercises").then(list => { for (const e of list) S.exNames[e.id] = e.name; renderAll(); fillSessions(); }).catch(() => {});
  try { await loadPatients(); } catch {}
  await pollState();                       // a running session wins: the screen opens on it
  if (!S.live) {
    const want = q.get("patient");
    const first = (want && S.patients.find(p => p.id === want)) || S.patients[0];
    await selectPatient(first ? first.id : null, q.get("session"));
  }
  setInterval(pollState, STATE_MS);
})();
