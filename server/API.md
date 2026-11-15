# Rehab station API: guide for Mat and Gio

Everything here runs on the arm laptop with no internet. All examples below are **real responses** copied from a running server (mock mode, so every value is simulated), with long numbers shortened.

**Rule: anything with `"simulated": true` must be shown as "simulated" on every screen, chart and slide.**

## 1. Start a feed to build against (no robot needed)

You need Python 3.12 once. From the repo folder:

```
py -3.12 -m venv server/.venv
server\.venv\Scripts\python -m pip install -r server/requirements.txt
server\.venv\Scripts\python -m server.simulate          (adds 14 days of SIMULATED history, once)
server\.venv\Scripts\python -m server.run --mock        (starts the server at http://127.0.0.1:8000)
```

Then start a pretend session from a second terminal:

```
curl -X POST http://127.0.0.1:8000/api/session/start -H "content-type: application/json" -d "{\"patient_id\":\"sim-demo\",\"display_name\":\"Demo\",\"dial\":1,\"auto\":true}"
```

Open `server/examples/live.html` in a browser: it shows the dial and reps updating live. That 25-line file is the smallest working example of everything below.

- Want to see it without a browser: `server\.venv\Scripts\python -m server.watch`
- Faster pretend patient: add `--time-scale 4`. Weaker patient: `--strength 0.2` (the dial then stays high).
- `--mock` is a stand-in until Shiv's engine is finished. Later the same routes come from `--sim` (simulated arm) or `--robot` (the real arm). **Your pages do not change.**
- Pages you put in `demo/site/` are served by the server at `http://127.0.0.1:8000/` automatically (restart the server after creating the folder).

## 2. Live feed: `ws://<laptop>:8000/ws/live`

Connect with a WebSocket; you do not need to send anything. Two kinds of message arrive.

**`sample`**, about 30 per second while a session runs:

```json
{"type": "sample", "t": 32.98, "pos": [0.474, 0.006, 0.3], "vel": [0.080, 0.0, 0.0],
 "force": [4.65, 0.0, 0.0], "target": [0.478, 0.006, 0.3], "dial": 0.4, "rep_idx": 4,
 "simulated": true, "phase": "out", "q": [0.048, 0.227, 0.3, 0.232, 0.054, -0.149, -0.282],
 "rep_count": 4, "auto": false, "arm_mode": "compliant"}
```

| Field | Meaning |
|-------|---------|
| `t` | seconds since the session started |
| `pos` | handle position x, y, z in metres (robot's frame). The reach is along one axis, about 0.30 m long |
| `vel` | handle speed per axis, m/s |
| `force` | force the person pushes the handle with, per axis, newtons. Bar length = `sqrt(x²+y²+z²)` |
| `target` | where the arm is pulling the handle toward. Draw it as a ghost dot ahead of (assist) or behind (resist) the hand |
| `dial` | **+1** the arm does the work, **0** free movement, **-1** maximum resistance |
| `phase` | `idle` (between reps), `out` (reaching), `back` (returning) |
| `rep_idx` | number of the rep in progress, -1 when idle |
| `rep_count` | reps finished so far |
| `auto` | true when the dial adjusts itself after each rep |
| `arm_mode` | `compliant` (normal), `hold` (stopped softly), `idle`, `fault` |
| `q` | 7 joint angles in radians, for a future 3D arm view |
| `simulated` | true unless the data comes from the real robot |

**`rep`**, once at the end of each repetition:

```json
{"type": "rep", "session_id": "20261114-135516-0968", "idx": 4, "mode": "assist", "dial": 0.4,
 "t_start": 32.2, "duration_s": 6.93, "rom_m": 0.3, "path_err_mean_m": 0.0052, "path_err_max_m": 0.0099,
 "sparc": -1.606, "peak_force_n": 7.45, "mean_force_n": 4.34, "contribution": 0.822,
 "completed": true, "simulated": true, "rescued": false}
```

Field meanings are the same as in `server/exports/README.md` (range of motion, path error, smoothness, force, contribution, and so on).

## 3. Reading data (GET)

| Route | Returns |
|-------|---------|
| `/api/health` | `{"ok": true, "arm": null, "arm_mode": null, "session": false, "arm_prepared": false}`. `arm` becomes `"sim"` or `"flexiv"` after the first session or prepare. `arm_prepared` turns true once `/api/arm/prepare` has succeeded on the real arm |
| `/api/state` | `{"session": null}` when nothing runs; otherwise the session plus the latest sample (example below) |
| `/api/patients` | list of patients |
| `/api/patients/{id}/sessions` | that patient's sessions, each with averages (same fields as `sessions.json`) |
| `/api/sessions/{id}/reps` | every rep of one session |
| `/api/sessions/{id}/note` | the automatic session note as plain text |

`/api/state` during a session:

```json
{"session": {"session_id": "20261114-135516-0968", "patient_id": "sim-demo", "simulated": true},
 "t": 31.27, "pos": [0.45, 0.0, 0.3], "dial": 0.4, "phase": "idle", "rep_count": 4, "auto": true,
 "arm_mode": "compliant", "...": "same fields as a sample"}
```

`/api/patients`:

```json
[{"id": "sim-anna", "display_name": "Anna (SIMULATED)", "simulated": true, "n_sessions": 3},
 {"id": "sim-demo", "display_name": "Demo (SIMULATED)", "simulated": true, "n_sessions": 1}]
```

`/api/patients/sim-anna/sessions` (first item):

```json
{"session_id": "sim-anna-d01-s1", "patient_id": "sim-anna", "started_at": "2026-10-31T09:30:00",
 "ended_at": "2026-10-31T09:37:19", "exercise": "reach_line", "n_reps": 30, "simulated": true,
 "mean_rom_m": 0.194, "mean_path_err_mean_m": 0.0293, "mean_sparc": -2.2303, "mean_peak_force_n": 4.311,
 "mean_contribution": 0.1914, "mean_duration_s": 6.7853, "dial_start": 0.945, "dial_end": 0.869,
 "mean_dial": 0.892, "completed_share": 0.967, "rescued_count": 9, "...": "more means"}
```

## 4. Controlling a session (POST, for the operator screen only)

| Route | Body | Does |
|-------|------|------|
| `/api/session/start` | `{"patient_id": "sim-demo", "display_name": "Demo", "dial": 1, "auto": true}` | starts a session. Returns `{"session_id": "...", "simulated": true, "display_name": "Demo (SIMULATED)"}`. The server decides `simulated`; you cannot set it |
| `/api/session/stop` | none | stops, saves, rewrites `server/exports/`. Returns the session summary |
| `/api/dial` | `{"dial": 0.4, "auto": false}` | sets the dial by hand (`auto: false`) or hands it back to auto (`auto: true`) |
| `/api/hold` | none | soft stop of the arm, any time |
| `/api/go` | none | only used if the arm cannot tell when the handle is held; may return 501 |
| `/api/shutdown` | none | **from the arm laptop only.** Stops any session, then the server exits cleanly: the arm is put in hold and closed (its normal stiffness restored). Returns `{"ok": true, "stopped_session": "..." or null}`. 403 from any other device. Use this (or Ctrl+C) instead of closing the server window |
| `/api/arm/prepare` | none | **real arm only, nobody touching the handle.** Checks the arm is connected and has no fault, zeroes the force reading, and returns the empty-handle force. Needed once after the server starts, before the first real session; safe to repeat between sessions |

Errors are JSON with a `detail` field: 409 `{"detail": "no session running"}` or "a session is already running", 404 for unknown ids, 422 for a bad body (for example dial above 1).

**Starting can be refused (409 or 503).** Show the `detail` text to the operator; nothing is running afterwards.

- 503 `"arm not connected: arm not ready: ..."`: the real arm is faulted, not enabled, not in IDLE, has its e-stop pressed or has the wrong tool selected. The server never clears faults or enables the robot by itself; fix it on the robot (see `robot/RUNBOOK.md`) and try again.

- `"prepare the arm first: POST /api/arm/prepare with nobody touching the handle"`: real arm, and prepare has not succeeded since the server started.
- `"session not started: ..."`: the engine refused, usually because the empty handle reads more than 3 N (someone is touching it, or the tool setting on the robot is wrong). Let go and call prepare again.

**`/api/arm/prepare` responses.**

Real arm:

```json
{"ok": true, "simulated": false, "zeroed": true, "zero_error": null,
 "baseline_force": [0.0, 0.0, 0.1], "baseline_n": 0.1}
```

- `baseline_force` is the mean force per axis in newtons with nobody touching, `baseline_n` its size. The engine refuses to start above 3 N.
- `zeroed: false` with a `zero_error` text means the robot's own zeroing step failed. That is not fatal (our Rizon 4 may not support it): the engine takes its own baseline at session start.
- Simulated and mock arms answer `{"ok": true, "simulated": true, "skipped": true, ...}` and never need prepare.
- 409 if a session is running or the arm reports a fault; 503 if the arm cannot be reached.
- It does not move the arm. Moving to the start pose (`home`) is not part of this route.

**On the venue network** the server is started with `--lan`. It then prints its address (for example `http://192.168.1.23:8000`, which a phone on the same Wi-Fi can open) and an operator token. Start, stop, dial, go, arm/prepare and shutdown then need the header `x-operator-token: <token>`, so nobody else on the Wi-Fi can drive the arm. Reading routes, the live feed and `/api/hold` stay open.

**Real-arm options of `python -m server.run --robot [SERIAL]`** (operator only):

| Option | Meaning |
|---|---|
| `--reach-m 0.10` | length of the reach line in metres (default 0.30, allowed 0.02 to 0.35) |
| `--reach-sign -1` | direction of the reach along the reach axis. Default: `"reach_sign"` in `robot/config.json` if present, else +1. The axis itself is `reach_axis` in that file |
| `--tool Flange` | tool that must be selected on the robot (default `Flange`, meaning nothing mounted); the server refuses to connect otherwise |

`--reach-m` and `--reach-sign` also work with `--sim` and `--mock`. Stop the server with Ctrl+C in its window or `curl -X POST http://127.0.0.1:8000/api/shutdown`; never by closing the window, which would leave the arm soft.

## 5. Ideas that the data already supports

- Patient screen: a horizontal track (start to end) with the hand as a dot from `pos`, the `target` as a ghost dot, a force bar, the dial as a big gauge, rep counter.
- Physio screen: rep table that grows on each `rep` message; per-session charts from `/api/patients/{id}/sessions` (dial falling, contribution and force rising); the note from `/api/sessions/{id}/note`.
- QR code to the physio page: only with `--lan`, and only after it works on the laptop itself.
