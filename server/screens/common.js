// Shared helpers for the live screens. Plain ES module, no build step, no internet.

const FALLBACK_HOST = "127.0.0.1:8000";
const fromFile = location.protocol === "file:" || !location.host;
const HOST = fromFile ? FALLBACK_HOST : location.host;
const SECURE = !fromFile && location.protocol === "https:";
const HTTP_BASE = `${SECURE ? "https" : "http"}://${HOST}`;
const WS_URL = `${SECURE ? "wss" : "ws"}://${HOST}/ws/live`;

// Live feed with auto-reconnect. onStatus gets "connecting", "live" or "lost".
export function connectLive(onSample, onRep, onStatus) {
  let ws = null, delay = 500, timer = null, closed = false;
  const status = s => { try { onStatus && onStatus(s); } catch (e) { console.error(e); } };

  function open() {
    if (closed) return;
    status("connecting");
    ws = new WebSocket(WS_URL);
    ws.onopen = () => { delay = 500; status("live"); };
    ws.onmessage = e => {
      let m;
      try { m = JSON.parse(e.data); } catch { return; }
      try {
        if (m.type === "sample") onSample && onSample(m);
        else if (m.type === "rep") onRep && onRep(m);
      } catch (err) { console.error(err); }
    };
    ws.onclose = () => {
      if (closed) return;
      status("lost");
      timer = setTimeout(open, delay);
      delay = Math.min(delay * 2, 5000);
    };
    ws.onerror = () => { try { ws.close(); } catch {} };
  }

  open();
  return { close() { closed = true; clearTimeout(timer); if (ws) ws.close(); } };
}

function operatorToken() {
  try { return localStorage.getItem("operatorToken"); } catch { return null; }
}

async function request(method, path, body) {
  const headers = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  if (method === "POST") {
    const tok = operatorToken();
    if (tok) headers["x-operator-token"] = tok;
  }
  const res = await fetch(HTTP_BASE + path, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data = text;
  try { data = text ? JSON.parse(text) : null; } catch {}
  if (!res.ok) {
    let detail = data && typeof data === "object" && "detail" in data ? data.detail : (text || res.statusText);
    if (typeof detail !== "string") detail = JSON.stringify(detail);
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  get: path => request("GET", path),
  post: (path, body) => request("POST", path, body),
};

// Only a strict false counts as the real robot; no data never shows as real.
export function simBanner(el, simulated) {
  if (!el) return;
  const [cls, text] = simulated === true ? ["sim", "SIMULATED"]
    : simulated === false ? ["real", "REAL ROBOT"] : ["none", "NO DATA"];
  el.className = `badge ${cls}`;
  el.textContent = text;
}

export function modeOf(dial) {
  return dial > 0.05 ? "assist" : dial < -0.05 ? "resist" : "free";
}

const num = x => typeof x === "number" && Number.isFinite(x);
const DASH = "–";
export const fmt = {
  cm: m => (num(m) ? `${(m * 100).toFixed(1)} cm` : DASH),
  N: n => (num(n) ? `${n.toFixed(1)} N` : DASH),
  pct: x => (num(x) ? `${Math.round(x * 100)}%` : DASH),
  s: x => (num(x) ? `${x.toFixed(1)} s` : DASH),
};
