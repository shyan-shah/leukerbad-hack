// Operator console logic. HOLD and the Space bar live in a plain script in operator.html,
// so they keep working if anything in this module fails.
import { connectLive, api, simBanner, fmt } from "./common.js";

const $ = id => document.getElementById(id);
const STALE_MS = 2000;                       // no samples for this long: no session is sending
const HEALTH_MS = 1500;
const SNAPS = [-1, -0.6, -0.3, 0, 0.3, 0.6, 1];
const SNAP_WITHIN = 0.05;
const ID_OK = /^[A-Za-z0-9_.-]{1,64}$/;
const TOKEN_KEY = "operatorToken";

let latest = null, lastAt = 0;               // newest sample and when it arrived
let health = null, healthFailed = false;
let wsStatus = "connecting";
let exercises = [];
let starting = false, homing = false;
let dialHoldUntil = 0, dragging = false;     // do not overwrite the slider from the feed while it is in use

// ---------------------------------------------------------------- small helpers
const signed = x => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(2);
const clock = () => new Date().toLocaleTimeString();
const fresh = () => latest !== null && performance.now() - lastAt < STALE_MS;
const running = () => fresh() || !!(health && health.session);

function setMsg(el, text, cls) { el.textContent = text; el.className = `msg ${cls || ""}`; }

function log(text, bad) {
  const li = document.createElement("li");
  li.textContent = `${clock()}  ${text}`;
  if (bad) li.className = "bad";
  $("log").prepend(li);
  while ($("log").children.length > 40) $("log").lastChild.remove();
}

function lastError(what, text) {
  $("sErr").textContent = `${clock()}  ${what}: ${text}`;
  $("sErr").className = "v bad";
  log(`${what} failed: ${text}`, true);
}

// The server's `detail` can be a sentence, an object with a message, or a list of field errors.
function cleanDetail(text) {
  try {
    const d = JSON.parse(text);
    if (d && typeof d === "object") {
      if (typeof d.message === "string") return d.message;
      if (Array.isArray(d)) return d.map(x => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`).join("; ");
    }
  } catch {}
  return text;
}

function explain(e) {
  if (e.status === undefined) return "No answer from the server. Is it still running? HOLD is sent separately.";
  const d = cleanDetail(e.message);
  if (e.status === 401 || (e.status === 403 && /token/i.test(d))) {
    $("token").classList.add("bad");
    setMsg($("tokenMsg"), "The server refused this token. Type the operator token printed in the server window and press Save.", "bad");
    return `Operator token missing or wrong (${e.status}). Enter it under Server. HOLD works without it.`;
  }
  return `${d} (${e.status})`;
}

// Runs one POST, shows the result in the panel's message line, returns the answer or undefined.
async function act(what, msgEl, path, body) {
  setMsg(msgEl, `${what}…`, "");
  act.lastStatus = undefined;
  try {
    const r = await api.post(path, body);
    $("token").classList.remove("bad");
    return r === null || r === undefined ? {} : r;
  } catch (e) {
    e.shown = explain(e);
    setMsg(msgEl, e.shown, "bad");
    lastError(what, e.shown);
    act.lastStatus = e.status;
    return undefined;
  }
}

// In-page confirm, kept below the HOLD button so HOLD stays clickable. Space never confirms.
function ask(title, text, okLabel) {
  return new Promise(resolve => {
    $("cTitle").textContent = title;
    $("cText").textContent = text;
    $("cOk").textContent = okLabel;
    const box = $("confirm");
    const done = yes => {
      box.hidden = true;
      $("cOk").onclick = $("cCancel").onclick = box.onkeydown = null;
      resolve(yes);
    };
    $("cOk").onclick = () => done(true);
    $("cCancel").onclick = () => done(false);
    box.onkeydown = e => { if (e.key === "Escape") done(false); };
    box.hidden = false;
    $("cCancel").focus();
  });
}

// ---------------------------------------------------------------- operator token
function readToken() { try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; } }
function writeToken(t) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY);
    return true;
  } catch { return false; }
}

function initToken() {
  const q = new URLSearchParams(location.search);
  const op = q.get("op");
  if (op) {
    const ok = writeToken(op.trim());
    q.delete("op");                           // keep the token out of the address bar
    const rest = q.toString();
    try { history.replaceState(null, "", location.pathname + (rest ? `?${rest}` : "") + location.hash); } catch {}
    setMsg($("tokenMsg"), ok ? "Token taken from the link and saved on this device." : "Could not save the token in this browser.", ok ? "ok" : "bad");
  } else {
    setMsg($("tokenMsg"), readToken() ? "A token is saved on this device." : "No token saved.", "");
  }
  $("token").value = readToken();
  $("tokenSave").onclick = () => {
    const t = $("token").value.trim();
    const ok = writeToken(t);
    $("token").classList.remove("bad");
    setMsg($("tokenMsg"), !ok ? "Could not save the token in this browser." : t ? "Token saved on this device." : "No token saved.", ok ? "ok" : "bad");
  };
  $("tokenClear").onclick = () => {
    writeToken("");
    $("token").value = "";
    $("token").classList.remove("bad");
    setMsg($("tokenMsg"), "No token saved.", "");
  };
  $("token").addEventListener("keydown", e => { if (e.key === "Enter") $("tokenSave").click(); });
}

// ---------------------------------------------------------------- arm panel
async function checkHome() {
  // Show Home only if this server has the route. Asking the route list never moves the arm.
  try {
    const spec = await api.get("/openapi.json");
    $("home").hidden = !(spec && spec.paths && spec.paths["/api/arm/home"] && spec.paths["/api/arm/home"].post);
  } catch {
    $("home").hidden = false;               // cannot tell: offer it, and hide it on a 404
  }
}

function showBaseline(r) {
  const el = $("baseline");
  el.hidden = false;
  el.textContent = "";
  const line = (strong, rest) => {
    const d = document.createElement("div");
    if (strong) { const b = document.createElement("b"); b.textContent = strong; d.append(b, " "); }
    d.append(rest);
    el.append(d);
  };
  if (r.skipped) {
    line("", `${r.simulated ? "SIMULATED arm" : "Arm"}: ${r.detail || "nothing to prepare"}. No baseline force measured.`);
    return;
  }
  const f = Array.isArray(r.baseline_force) ? r.baseline_force : null;
  line(fmt.N(r.baseline_n), `baseline force with nobody touching${r.simulated ? " (SIMULATED)" : ""}`);
  if (f) line("", `per axis: x ${fmt.N(f[0])}, y ${fmt.N(f[1])}, z ${fmt.N(f[2])}`);
  if (typeof r.from_start_m === "number") line("", `handle ${(r.from_start_m * 100).toFixed(1)} cm from the start pose`);
  if (r.zeroed === false) line("", `The robot's own zeroing step failed (${r.zero_error || "no reason given"}). Not fatal: the engine takes its own baseline at session start.`);
  else if (r.zeroed === true) line("", "Force reading zeroed.");
}

async function doHome() {
  if (!await ask("Move the arm to the start pose?",
    "The arm will move by itself, slowly, to the start pose. Nobody holds the handle and nobody stands inside its reach. HOLD does NOT stop this move: only the e-stop does. Have a hand on the e-stop.", "Move to home")) return;
  homing = true; render();
  const r = await act("Home (arm moving; only the e-stop stops it)", $("armMsg"), "/api/arm/home");
  homing = false; render();
  if (r === undefined) {
    if (act.lastStatus === 404) {
      $("home").hidden = true;
      setMsg($("armMsg"), "This server has no Home route yet (404). Move the arm to the start pose on the robot, then Prepare.", "bad");
    }
    return;
  }
  const cm = m => (typeof m === "number" ? `${(m * 100).toFixed(1)} cm` : "?");
  const text = r.skipped ? `Home skipped: ${r.detail || "nothing to home"}.`
    : "moved_m" in r ? `Home done: moved ${cm(r.moved_m)}, now ${cm(r.from_start_m)} from the start pose. Prepare again before a session.`
    : `Home done. ${typeof r.detail === "string" ? r.detail : JSON.stringify(r)}`;
  $("baseline").hidden = true;                // any earlier baseline no longer applies
  setMsg($("armMsg"), text, "ok");
  log(text);
  pollHealth();
}

async function doPrepare() {
  $("prepare").disabled = true;
  const r = await act("Prepare", $("armMsg"), "/api/arm/prepare");
  $("prepare").disabled = false;
  if (r === undefined) { $("baseline").hidden = true; return; }
  showBaseline(r);
  setMsg($("armMsg"), r.skipped ? "Prepare skipped." : "Arm prepared.", "ok");
  log(r.skipped ? "Prepare skipped (simulated arm)" : `Prepared: baseline ${fmt.N(r.baseline_n)}`);
  pollHealth();
}

// ---------------------------------------------------------------- session panel
async function loadExercises() {
  try {
    exercises = await api.get("/api/exercises");
  } catch {
    setTimeout(loadExercises, 3000);
    return;
  }
  const sel = $("exercise"), keep = sel.value;
  sel.textContent = "";
  for (const e of exercises) {
    const o = document.createElement("option");
    o.value = e.id;
    o.textContent = `${e.name} (${e.id})`;
    sel.append(o);
  }
  if (exercises.some(e => e.id === keep)) sel.value = keep;
  exerciseChanged();
}

const exInfo = id => exercises.find(e => e.id === id);
const exName = id => (exInfo(id) || {}).name || id || "–";

function exerciseChanged() {
  const e = exInfo($("exercise").value);
  $("reps").value = "";
  $("reps").placeholder = e ? `${e.reps} (default)` : "";
}

async function doStart() {
  const ex = $("exercise").value, pid = $("pid").value.trim(), pname = $("pname").value.trim();
  const repsText = $("reps").value.trim();
  $("pid").classList.toggle("bad", !ID_OK.test(pid));
  if (!ex) return setMsg($("sessionMsg"), "No exercise list from the server yet.", "bad");
  if (!ID_OK.test(pid)) return setMsg($("sessionMsg"), "Patient id: 1 to 64 letters, digits, _ . or - (no spaces).", "bad");
  const body = { patient_id: pid, exercise: ex };
  if (pname) body.display_name = pname;
  let repsWord = `${(exInfo(ex) || {}).reps ?? "default"} reps (default)`;
  if (repsText !== "") {
    const n = Number(repsText);
    if (!Number.isInteger(n) || n < 0) return setMsg($("sessionMsg"), "Reps must be a whole number, 0 or more.", "bad");
    body.reps = n;
    repsWord = n === 0 ? "no rep limit (until Stop)" : `${n} reps`;
  }
  const yes = await ask("Start the session?",
    `${exName(ex)}, ${repsWord}, patient ${pname || pid} (${pid}). The arm becomes active as soon as you confirm.`, "Start");
  if (!yes) return;
  starting = true; render();
  const r = await act("Start", $("sessionMsg"), "/api/session/start", body);
  starting = false;
  if (r !== undefined) {
    if (health) health.session = true;
    setMsg($("sessionMsg"), `Running: ${exName(r.exercise)}, session ${r.session_id}, ${r.display_name}.`, "ok");
    log(`Started ${r.exercise} for ${r.display_name}: session ${r.session_id}${r.simulated ? " (SIMULATED)" : ""}`);
    document.activeElement && document.activeElement.blur();
  }
  render();
  pollHealth();
}

async function doStop() {
  $("stop").disabled = true;
  const r = await act("Stop", $("sessionMsg"), "/api/session/stop");
  $("stop").disabled = false;
  if (r !== undefined) {
    latest = null;
    if (health) health.session = false;
    const el = $("sessionMsg");
    setMsg(el, `Stopped and saved: ${r.n_reps} rep${r.n_reps === 1 ? "" : "s"}, session ${r.session_id}${r.simulated ? " (SIMULATED)" : ""}. `, "ok");
    const a = document.createElement("a");
    a.href = `physio.html?patient=${encodeURIComponent(r.patient_id)}&session=${encodeURIComponent(r.session_id)}`;
    a.target = "_blank"; a.rel = "noopener";
    a.textContent = "Open on the physio screen";
    el.append(a);
    log(`Stopped session ${r.session_id}: ${r.n_reps} reps`);
  }
  render();
  pollHealth();
}

// ---------------------------------------------------------------- dial
function snap(v) {
  for (const s of SNAPS) if (Math.abs(v - s) <= SNAP_WITHIN) return s;
  return Math.round(v * 100) / 100;
}

async function sendDial(value, auto) {
  dialHoldUntil = performance.now() + 800;
  const r = await act(auto ? "Return to auto" : "Dial", $("dialMsg"), "/api/dial", { dial: value, auto });
  if (r === undefined) { dialHoldUntil = 0; return; }
  setMsg($("dialMsg"), auto ? "Dial handed back to auto." : `Dial set to ${signed(r.dial)} by hand.`, "ok");
  log(auto ? "Dial returned to auto" : `Dial set to ${signed(r.dial)}`);
}

function initDial() {
  const slider = $("dial");
  for (const s of SNAPS) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = signed(s); b.dataset.v = s; b.disabled = true;
    b.onclick = () => { slider.value = s; $("dialNow").textContent = signed(s); sendDial(s, false); };
    $("snaps").append(b);
  }
  slider.addEventListener("pointerdown", () => { dragging = true; });
  slider.addEventListener("input", () => {
    dragging = true;
    $("dialNow").textContent = signed(snap(Number(slider.value)));
  });
  const release = () => { dragging = false; };
  slider.addEventListener("pointerup", release);
  slider.addEventListener("pointercancel", release);
  slider.addEventListener("blur", release);
  slider.addEventListener("change", () => {          // fires when the slider is let go
    dragging = false;
    const v = snap(Number(slider.value));
    slider.value = v;
    sendDial(v, false);
  });
  $("auto").onclick = () => sendDial(Number(slider.value), true);
}

// ---------------------------------------------------------------- server panel
async function doShutdown() {
  const yes = await ask("Shut down the server?",
    "Stops any running session, holds and closes the arm, then the server exits. All screens lose their connection until it is started again.",
    "Shut down");
  if (!yes) return;
  const r = await act("Shutdown", $("serverMsg"), "/api/shutdown");
  if (r === undefined) return;
  setMsg($("serverMsg"), `Server is shutting down${r.stopped_session ? ` (stopped session ${r.stopped_session})` : ""}. Start it again from its window.`, "ok");
  log("Server shutdown requested");
}

// ---------------------------------------------------------------- live status
async function pollHealth() {
  try {
    health = await api.get("/api/health");
    healthFailed = false;
  } catch {
    health = null;
    healthFailed = true;
  }
  render();
}

function render() {
  const run = running(), m = fresh() ? latest : null;
  window.vitaSessionRunning = run;          // read by the HOLD script: Space always holds during a session

  $("dot").className = `dot ${wsStatus}`;
  $("conn").textContent = wsStatus === "live" ? (healthFailed ? "feed only" : "live") : wsStatus;

  const mode = m ? m.arm_mode : health ? health.arm_mode : null;
  const known = ["compliant", "hold", "idle", "fault"].includes(mode);
  $("armMode").textContent = mode || (health && health.arm === null ? "not connected" : "–");
  $("armMode").className = `pill am-${known ? mode : "none"}`;

  $("sEx").textContent = m ? exName(m.exercise) : run ? "…" : "no session";
  $("sPhase").textContent = m ? m.phase : "–";
  $("sReps").textContent = m ? `${m.rep_count ?? 0} of ${m.reps_target ?? "∞"}` : "–";
  $("sDial").textContent = m ? `${signed(m.dial)} ${m.auto ? "auto" : "manual"}` : "–";
  $("sForce").textContent = m ? fmt.N(Math.hypot(...(m.force || [0, 0, 0]))) : "–";
  simBanner($("badge"), m ? m.simulated : health && health.arm === "flexiv" ? false : health && health.arm === "sim" ? true : undefined);

  // controls
  $("start").disabled = run || starting || homing;
  for (const id of ["exercise", "reps", "pid", "pname"]) $(id).disabled = run || starting;
  $("prepare").disabled = run || homing;
  $("home").disabled = run || homing;
  $("dial").disabled = !run;
  $("auto").disabled = !run;
  for (const b of $("snaps").children) b.disabled = !run;
  $("stop").classList.toggle("attn", !!(m && (m.done || m.arm_mode === "hold" || m.arm_mode === "fault")));

  if (m && !dragging && performance.now() > dialHoldUntil) {
    $("dial").value = m.dial;
    $("dialNow").textContent = signed(m.dial);
  }
  if (!m) $("dialNow").textContent = "–";
  $("autoTag").textContent = m ? (m.auto ? "AUTO" : "MANUAL") : "–";
  $("autoTag").className = `tag ${m && m.auto ? "on" : ""}`;

  // one line that says what the operator should do next
  const alert = $("alert");
  let text = "", stop = false;
  if (homing) { text = "ARM MOVING TO THE START POSE. HOLD does not stop this move: use the e-stop if anything is wrong."; stop = true; }
  else if (m && m.arm_mode === "fault") { text = "ARM FAULT. The arm has stopped. Press Stop and save, then see robot/RUNBOOK.md."; stop = true; }
  else if (m && m.arm_mode === "hold") { text = "Arm is in HOLD. Press Stop and save to end this session; start a new one to continue."; stop = true; }
  else if (m && m.done) text = "Set finished. Press Stop and save.";
  else if (healthFailed && wsStatus !== "live") { text = "The server is not answering. Check its window. If the arm is moving, use the e-stop."; stop = true; }
  else if (!run && health && health.arm_mode === "hold") text = "Arm is in hold (normal between sessions).";
  alert.hidden = !text;
  alert.textContent = text;
  alert.className = `alert ${stop ? "stop" : ""}`;
}

// ---------------------------------------------------------------- wiring
initToken();
initDial();
$("home").onclick = doHome;
$("prepare").onclick = doPrepare;
$("exercise").onchange = exerciseChanged;
$("start").onclick = doStart;
$("stop").onclick = doStop;
$("shutdown").onclick = doShutdown;
$("pid").addEventListener("input", () => $("pid").classList.toggle("bad", !ID_OK.test($("pid").value.trim())));
window.addEventListener("vita-hold", e => {
  if (e.detail.state === "sent") log("HOLD sent");
  if (e.detail.state === "failed") lastError("HOLD", e.detail.text);
  if (e.detail.state !== "sending") pollHealth();
});

connectLive(
  m => { latest = m; lastAt = performance.now(); },
  r => log(`Rep ${r.idx + 1} (${r.mode}): peak ${fmt.N(r.peak_force_n)}${r.completed ? "" : ", not completed"}${r.rescued ? ", rescued" : ""}`),
  s => { wsStatus = s; if (s !== "live") latest = null; render(); },
);
loadExercises();
checkHome();
pollHealth();
setInterval(pollHealth, HEALTH_MS);
setInterval(render, 100);
