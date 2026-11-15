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
| `phase` | `idle` (between reps), `out` (reaching, pushing, pulling, or a strength-test try), `back` (returning), `setup` (`pull` only: the patient is moving the handle to the far end before the first rep) |
| `exercise` | programme id of the session: `reach`, `push`, `pull`, `armtest` (section 6) |
| `reps_target` | reps planned for this session (asked for at start, else the exercise default) |
| `done` | true once `rep_count` has reached `reps_target`: the set is finished, call stop |
| `rep_idx` | number of the rep in progress, -1 when idle |
| `rep_count` | reps finished so far |
| `auto` | true when the dial adjusts itself after each rep |
| `arm_mode` | `compliant` (normal), `hold` (stopped softly), `idle`, `fault` |
| `arm_fault` | Why the arm stopped, while `arm_mode` is `hold` or `fault`: the trip text, for example `"speed 0.44 m/s above 0.40 m/s"` or `"hand 3.4 cm outside workspace box on axis y"`; otherwise `null` (a hold with `null` is an ordinary stop). After a trip no rep can start in that session: show the text, tell the person to let go, then stop the session, home, prepare and start again. In `/api/state` and every `sample` message |
| `q` | 7 joint angles in radians, for a future 3D arm view |
| `simulated` | true unless the data comes from the real robot |

**`rep`**, once at the end of each repetition:

```json
{"type": "rep", "session_id": "20261114-135516-0968", "idx": 4, "mode": "assist", "dial": 0.4,
 "t_start": 32.2, "duration_s": 6.93, "rom_m": 0.3, "path_err_mean_m": 0.0052, "path_err_max_m": 0.0099,
 "sparc": -1.606, "peak_force_n": 7.45, "mean_force_n": 4.34, "contribution": 0.822,
 "completed": true, "simulated": true, "rescued": false}
```

Field meanings are the same as in `server/exports/README.md` (range of motion, path error, smoothness, force, contribution, and so on). Messages now also carry `"exercise"`. `mode` is `assist`, `transparent`, `resist`, or `isometric` for a strength-test try (then only `peak_force_n`, `mean_force_n` and `duration_s` mean something).

## 3. Reading data (GET)

| Route | Returns |
|-------|---------|
| `/api/health` | `{"ok": true, "arm": null, "arm_mode": null, "session": false, "arm_prepared": false}`. `arm` becomes `"sim"` or `"flexiv"` after the first session or prepare. `arm_prepared` turns true once `/api/arm/prepare` has succeeded on the real arm |
| `/api/state` | `{"session": null}` when nothing runs; otherwise the session plus the latest sample (example below) |
| `/api/exercises` | the programmes the robot can run now, each with `id`, `name`, `kind` and default `reps` (section 6) |
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
 "ended_at": "2026-10-31T09:37:19", "exercise": "reach", "n_reps": 30, "simulated": true,
 "mean_rom_m": 0.194, "mean_path_err_mean_m": 0.0293, "mean_sparc": -2.2303, "mean_peak_force_n": 4.311,
 "mean_contribution": 0.1914, "mean_duration_s": 6.7853, "dial_start": 0.945, "dial_end": 0.869,
 "mean_dial": 0.892, "completed_share": 0.967, "rescued_count": 9, "...": "more means"}
```

## 4. Controlling a session (POST, for the operator screen only)

| Route | Body | Does |
|-------|------|------|
| `/api/session/start` | `{"patient_id": "sim-demo", "display_name": "Demo", "exercise": "push", "reps": 10}` | starts a session. Only `patient_id` is required. `exercise` defaults to `reach`; `reps` defaults to the exercise's own number (`0` = keep going past it until stop; a strength test always ends after its tries); `dial` and `auto` are optional and, when left out, the exercise's own settings apply (reach starts at +1 with auto on, push and pull at -0.6 with auto off). Returns `{"session_id": "...", "simulated": true, "display_name": "Demo (SIMULATED)", "exercise": "push", "reps": 10}`. The server decides `simulated`; you cannot set it |
| `/api/session/stop` | none | stops, saves, rewrites `server/exports/`. Returns the session summary |
| `/api/dial` | `{"dial": 0.4, "auto": false}` | sets the dial by hand (`auto: false`) or hands it back to auto (`auto: true`) |
| `/api/hold` | none | soft stop of the arm, any time |
| `/api/go` | none | only used if the arm cannot tell when the handle is held; may return 501 |
| `/api/shutdown` | none | **from the arm laptop only.** Stops any session, then the server exits cleanly: the arm is put in hold and closed (its normal stiffness restored). Returns `{"ok": true, "stopped_session": "..." or null}`. 403 from any other device. Use this (or Ctrl+C) instead of closing the server window |
| `/api/arm/home` | none | **real arm only, nobody touching: this moves the arm.** Slow straight move (0.05 m/s) to the start pose in `robot/config.json`. The call answers when the arm is there. Prepare is needed again afterwards |
| `/api/arm/prepare` | none | **real arm only, nobody touching the handle.** Checks the arm is connected, has no fault and is within 2 cm of the start pose, zeroes the force reading (`ZeroFTSensor`), and returns the empty-handle force. Needed once after the server starts, before the first real session, and after every home; safe to repeat between sessions |
| `/api/exercises/enable` | `{"ids": ["push"]}` | operator: start offering these exercises (they must be ones the robot can run). Returns `{"ok": true, "enabled": [...], "can_run": [...]}` |
| `/api/exercises/disable` | `{"ids": ["pull"]}` | operator: stop offering these exercises. A running session is not affected |

Errors are JSON with a `detail` field: 409 `{"detail": "no session running"}` or "a session is already running", 404 for unknown ids, 422 for a bad body (for example dial above 1, or an exercise that is not live: section 6).

**Starting can be refused (409 or 503).** Show the `detail` text to the operator; nothing is running afterwards.

- 503 `"arm not connected: arm not ready: ..."`: the real arm is faulted, not enabled, not in IDLE, has its e-stop pressed or has the wrong tool selected. The server never clears faults or enables the robot by itself; fix it on the robot (see `robot/RUNBOOK.md`) and try again.

- `"prepare the arm first: POST /api/arm/prepare with nobody touching the handle"`: real arm, and prepare has not succeeded since the server started.
- `"session not started: ..."`: the engine refused, usually because the empty handle reads more than 3 N (someone is touching it, or the tool setting on the robot is wrong). Let go and call prepare again.

**`/api/arm/prepare` responses.**

Real arm:

```json
{"ok": true, "simulated": false, "zeroed": true, "zero_error": null,
 "baseline_force": [0.0, 0.0, 0.1], "baseline_n": 0.1, "from_start_m": 0.0012}
```

- `baseline_force` is the mean force per axis in newtons with nobody touching, `baseline_n` its size. The engine refuses to start above 3 N.
- `zeroed: false` with a `zero_error` text means the robot's own zeroing step failed. That is not fatal (our Rizon 4 may not support it): the engine takes its own baseline at session start.
- Simulated and mock arms answer `{"ok": true, "simulated": true, "skipped": true, ...}` and never need prepare.
- `from_start_m` is how far the handle is from the start pose (null while `robot/config.json` still has a placeholder start pose).
- 409 `"the handle is 28.0 cm from the start pose; return it first: POST /api/arm/home, nobody touching. Not zeroed."` if the handle is more than 2 cm from the start pose. Zeroing anywhere else would be wrong at the start: the empty reading changes by up to 3 N along the reach.
- 409 if a session is running or the arm reports a fault; 503 if the arm cannot be reached.
- It does not move the arm. Returning to the start pose is a separate, explicit operator action (`/api/arm/home`).

**`/api/arm/home` responses.** Real arm: `{"ok": true, "simulated": false, "moved_m": 0.28, "from_start_m": 0.0004}` (distance before and after). 409 `"home refused or failed: ..."` when the arm refuses (placeholder start pose, more than 0.60 m away, a robot fault, or it ended more than 2 cm off), 409 during a session or with a fault, 503 if the arm cannot be reached. Simulated and mock arms answer `skipped`. **`/api/hold` does not interrupt a home in progress; the e-stop does.** There is no operator screen yet, so both are called by hand, in this order, with nobody touching the arm:

```
curl -X POST http://127.0.0.1:8000/api/arm/home
curl -X POST http://127.0.0.1:8000/api/arm/prepare
```

With `--lan` add the operator token to each:

```
curl -X POST -H "x-operator-token: TOKEN" http://127.0.0.1:8000/api/arm/home
curl -X POST -H "x-operator-token: TOKEN" http://127.0.0.1:8000/api/arm/prepare
```

**Enabling exercises one at a time.** `python -m server.run --robot --exercises reach` offers only `reach` at start-up (`/api/exercises` lists only that, anything else is refused with 422). Add more while the server runs:

```
curl -X POST -H "Content-Type: application/json" -H "x-operator-token: TOKEN" -d "{\"ids\": [\"push\"]}" http://127.0.0.1:8000/api/exercises/enable
```

(leave the token header out without `--lan`; `/api/exercises/disable` takes the same body). Ids that the robot cannot run are refused with 422 and the list it can run. Without `--exercises`, everything the robot can run is offered, as before.

**On the venue network** the server is started with `--lan`. It then prints its address (for example `http://192.168.1.23:8000`, which a phone on the same Wi-Fi can open) and an operator token. Start, stop, dial, go, arm/home, arm/prepare, exercises/enable, exercises/disable and shutdown then need the header `x-operator-token: <token>`, so nobody else on the Wi-Fi can drive the arm. Reading routes, the live feed and `/api/hold` stay open.

**Real-arm options of `python -m server.run --robot [SERIAL]`** (operator only):

| Option | Meaning |
|---|---|
| `--reach-m 0.10` | length of the reach line in metres (default 0.30, allowed 0.02 to 0.35) |
| `--reach-sign -1` | direction of the reach along the reach axis. Default: `"reach_sign"` in `robot/config.json` if present, else +1. The axis itself is `reach_axis` in that file |
| `--tool Flange` | tool that must be selected on the robot (default `Flange`, meaning nothing mounted); the server refuses to connect otherwise |
| `--exercises reach` | comma list of exercises offered at start-up (default: all the robot can run). More are added with `POST /api/exercises/enable` |

`--reach-m` and `--reach-sign` also work with `--sim` and `--mock`. Stop the server with Ctrl+C in its window or `curl -X POST http://127.0.0.1:8000/api/shutdown`; never by closing the window, which would leave the arm soft.

## 5. Ideas that the data already supports

- Patient screen: a horizontal track (start to end) with the hand as a dot from `pos`, the `target` as a ghost dot, a force bar, the dial as a big gauge, rep counter.
- Physio screen: rep table that grows on each `rep` message; per-session charts from `/api/patients/{id}/sessions` (dial falling, contribution and force rising); the note from `/api/sessions/{id}/note`.
- QR code to the physio page: only with `--lan`, and only after it works on the laptop itself.


## 6. Running an exercise from the app (for Mat)

One exercise = one session. The whole flow is five calls. Every example below is a **real message** from a running server with the mock engine (`--mock`, so everything is simulated), numbers shortened.

**Which exercises work today.** `reach`, `push`, `pull` and `armtest`, on `--mock`, `--sim` and `--robot`. With `--sim` and `--robot` the list comes from the robot side (`software/exercises.py`), so if one is switched off (the operator can also switch them on and off while the server runs) or `circle` is switched on, `/api/exercises` changes with no change on your side (`--mock` always offers these four). Build the screen from `/api/exercises`, not from a fixed list. (On the real arm only `reach` has been run so far; the other three are tested on the simulated arm.)

### Step 1. Ask what the robot can do

`GET /api/exercises`

```json
[{"id": "reach", "name": "Forward reach (assisted)", "kind": "assist", "reps": 10},
 {"id": "push", "name": "Push (resisted)", "kind": "resist", "reps": 10},
 {"id": "pull", "name": "Row (resisted)", "kind": "resist", "reps": 10},
 {"id": "armtest", "name": "Push strength test", "kind": "test", "reps": 3}]
```

The `id`s are the same as in your app's `EX` library. Anything in `EX` that is not in this list is animation only: do not send it to the robot. `reps` is the default number of reps (for `armtest`: tries).

### Step 2. Start

`POST /api/session/start` with `{"patient_id": "sim-demo", "exercise": "push", "reps": 3}`

```json
{"session_id": "20261115-124334-37ff", "simulated": true, "display_name": "sim-demo (SIMULATED)",
 "exercise": "push", "reps": 3}
```

- `patient_id`: letters, digits, `_`, `.` and `-` only. Add `"display_name"` if you want a name stored.
- Leave out `reps` to get the default from step 1. Leave out `dial` and `auto`: each exercise brings its own.
- On the venue network add the header `x-operator-token` (section 4).
- An exercise that is not live gives 422, with the list of what is:

```json
{"detail": {"message": "exercise 'knee' is not live on the robot. Live exercises: reach, push, pull, armtest",
            "live": ["reach", "push", "pull", "armtest"]}}
```

- 409 or 503 means the session did not start; `detail` is a sentence for the operator (section 4).

### Step 3. Listen on `ws://<laptop>:8000/ws/live`

About 30 `sample` messages a second, and one `rep` message when each rep ends. Use `phase` for the prompt, `force` for a live bar, `rep_count` and `reps_target` for "3 of 10".

`push`, while pushing out (the `target` sits behind the hand: that is the resistance):

```json
{"type": "sample", "t": 1.78, "pos": [0.467, 0.006, 0.3], "vel": [0.057, 0.0, 0.0],
 "force": [3.541, 0.0, 0.0], "target": [0.417, 0.006, 0.3], "dial": -0.6, "rep_idx": 0,
 "simulated": true, "phase": "out", "q": [0.036, 0.219, 0.3, 0.239, 0.066, -0.138, -0.277],
 "rep_count": 0, "auto": false, "arm_mode": "compliant", "exercise": "push", "reps_target": 3, "done": false}
```

`push`, a finished rep:

```json
{"type": "rep", "session_id": "20261115-124334-37ff", "idx": 0, "mode": "resist", "dial": -0.6,
 "t_start": 1.0, "duration_s": 7.74, "rom_m": 0.28, "path_err_mean_m": 0.007, "path_err_max_m": 0.013,
 "sparc": -1.787, "peak_force_n": 13.13, "mean_force_n": 8.48, "contribution": 0.748,
 "completed": true, "simulated": true, "rescued": false, "exercise": "push"}
```

`pull` starts with a `setup` phase: the arm moves freely (`dial` is 0) while the patient moves the handle to the far end, then the reps run from there towards the body. Show "Move the handle to the far end" while `phase` is `setup`:

```json
{"type": "sample", "t": 0.05, "pos": [0.45, 0.0, 0.3], "vel": [0.0, 0.0, 0.0], "force": [0.0, 0.0, 0.0],
 "target": [0.45, 0.0, 0.3], "dial": 0.0, "rep_idx": -1, "simulated": true, "phase": "setup",
 "q": [0.0, 0.193, 0.296, 0.259, 0.101, -0.105, -0.262], "rep_count": 0, "auto": false,
 "arm_mode": "compliant", "exercise": "pull", "reps_target": 2, "done": false}
```

A pull session ends with the handle at the far end. Move it back to the start before the next exercise (see the note under step 4).

`armtest` (strength test): the arm holds the handle in place (it gives way a few centimetres under a hard push) and the patient pushes for 3 seconds, 3 tries, with 5 seconds of rest between tries. The phases are `idle`, then for each try `out` (push now) followed by `back` with `rep_idx` -1 (rest), and `idle` again after the last try. During `out` show "Push and hold" and a bar from `force`; during `back` show "Rest":

```json
{"type": "sample", "t": 1.44, "pos": [0.478, 0.0, 0.3], "vel": [0.0, 0.0, 0.0],
 "force": [16.708, 0.0, 0.0], "target": [0.478, 0.0, 0.3], "dial": 0.0, "rep_idx": 0,
 "simulated": true, "phase": "out", "q": [0.055, 0.232, 0.3, 0.227, 0.047, -0.155, -0.284],
 "rep_count": 0, "auto": false, "arm_mode": "compliant", "exercise": "armtest", "reps_target": 3, "done": false}
```

Each try ends with a `rep` whose `mode` is `isometric`. The result is `peak_force_n`; the best try is the highest one. `completed` is false for a try with almost no push or one that moved the handle too far. Ignore `rom_m` (how far the handle gave way), `sparc`, `contribution` and the path errors for this exercise:

```json
{"type": "rep", "session_id": "20261115-124340-b01d", "idx": 0, "mode": "isometric", "dial": 0.0,
 "t_start": 1.0, "duration_s": 3.0, "rom_m": 0.048, "path_err_mean_m": 0.0, "path_err_max_m": 0.0,
 "sparc": 0.0, "peak_force_n": 28.65, "mean_force_n": 23.35, "contribution": 1.0,
 "completed": true, "simulated": true, "rescued": false, "exercise": "armtest"}
```

Readings stop at about 30 N: that is the robot's safety limit, not the patient's. Say so next to the number.

**What to show from a rep:** reach in cm = `rom_m * 100`, peak force = `peak_force_n` N, contribution = `contribution * 100` % (reach only; our own index). If `"simulated": true`, label it simulated.

**When is the set finished?** When a `sample` has `"done": true` (`rep_count` has reached `reps_target`). The server does not stop by itself: the session stays open and resting until you call stop.

```json
{"type": "sample", "t": 26.43, "pos": [0.45, 0.0, 0.3], "force": [0.0, 0.0, 0.0], "dial": -0.6,
 "rep_idx": -1, "phase": "idle", "rep_count": 3, "arm_mode": "compliant", "exercise": "push",
 "reps_target": 3, "done": true, "...": "other sample fields"}
```

If `arm_mode` becomes `hold` or `fault`, the arm has stopped safely: show "Arm stopped, please wait" and call stop. No WebSocket? Poll `GET /api/state` a few times a second; it has the same fields.

### Step 4. Stop

`POST /api/session/stop` (no body)

```json
{"session_id": "20261115-124334-37ff", "patient_id": "sim-demo", "started_at": "2026-11-15T12:43:34",
 "ended_at": "2026-11-15T12:43:36", "exercise": "push", "n_reps": 3, "simulated": true}
```

Always call it, also when the patient gives up early. Then start the next exercise of the plan with step 2. Every exercise starts from the start position, so after a `pull` (which ends at the far end) the handle has to be brought back first; simplest is to put `pull` last in a plan. All reps of the session: `GET /api/sessions/{session_id}/reps`.

### Step 5. Get the note

`GET /api/sessions/20261115-124340-b01d/note` returns plain text, ready to show or paste. For the strength test:

```
Drafted automatically from device data for therapist review. Not a clinical assessment.
SIMULATED DATA: not from a real patient.

Patient: sim-demo    Session: 20261115-124340-b01d
Started: 2026-11-15T12:43:40    Ended: 2026-11-15T12:43:41
Exercise: push strength test: the handle is held still while the person pushes (isometric)

Tries: 3
Peak force: best 29.1 N, mean 28.6 N over the tries

Try         Peak      Mean     Held
1         28.6 N    23.4 N    3.0 s
2         29.1 N    24.0 N    3.0 s
3         27.9 N    22.9 N    3.0 s

Readings capped at about 30 N by the robot's safety limit.
Force is measured along the push direction with the handle held still; it is a device reading, not a clinically validated strength score.
Therapist comments: ______________________________
```

For reach, push and pull the note starts with one summary line, then the full table:

```
Summary: 3 reps, range 28.0 cm (mean), peak force 13.7 N (best), resistance level 60% of maximum (mean dial -0.60), mean force 8.5 N
```

### Trying it without the robot

`python -m server.run --mock --time-scale 4` (add `--strength 0.3` for a weaker pretend patient). The mock engine plays all four exercises, stops at the rep count and rests. Its numbers are made up to look plausible.
