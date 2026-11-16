# Exercise map: Mat's app → what the robot does

Source: `demo/app/index.html` (Mat, 15 Nov). The app's exercise library is `EX` and the 3D motion of each exercise is `MOV` (hand path in the 3D scene, metres; scene x = forward from the patient, y = up, z = sideways). This file says which exercises the real Flexiv Rizon 4 performs, how, and with what settings, so the app, the server and the engine agree.

Robot constraints that decide this: handle on the flange (no shin cuff), per-axis Cartesian stiffness (straight-line tunnel along one world axis is native; curved tunnels are not), workspace about ±5 cm across the reach line and 0.30 m along it (Layout B: reach along world y at x ≈ 0.50), arm.py limits (600 N/m, 5 cm lead, 0.15 m/s, 40 N trip).

## Live on the robot for the pitch (MUST)

| App id | App name | App motion (`MOV`) | Robot implementation | Engine settings |
|---|---|---|---|---|
| `reach` | Forward reach (Assisted) | hand forward about 0.34 m with a slight rise | Existing engine: straight reach along the reach axis, assist as needed | `reach_m 0.30`, dial starts +1, `auto: true` |
| `push` | Push (Resisted) | hand forward 0.28 m | Same line, resistance side of the dial | `reach_m 0.28`, dial -0.6, `auto: false` (or auto with floor -0.6) |
| `pull` | Row (Resisted) | hand towards the body 0.28 m | Same line, reversed: start at the far end, "out" phase moves towards the patient, resistance band pulls back to the far end | `reach_m 0.28`, `reach_sign` = minus the push sign, start pose = far end, dial -0.6 |
| `armtest` (fig `pushhold`) | Push strength test (Test) | hand still, pushes forward, 3 tries | New isometric mode: hold position at high stiffness (`K_HOLD`, inside limits), patient pushes 3 s, record peak and mean force along the reach axis per try. No motion beyond about 1 cm | 3 tries, 3 s each, report peak N |

These four cover the "Strength" plan (Sofie: push, pull, armtest; skip knee) and most of the "Arm recovery" plan (Maria: reach; replace trace and lift, see below).

## Possible if time allows (SHOULD, robot-led, isotropic stiffness)

| App id | App motion | Robot implementation | Risk |
|---|---|---|---|
| `circle` | circle radius 0.13 m in the vertical plane | Robot-led: the target moves around a circle at a fixed slow pace; the same stiffness on all 3 axes (e.g. 300 N/m); no assist-as-needed, no tunnel. Scale to radius ≤ 0.08 m to stay inside the workspace | Medium: needs a new path type and a workspace check |
| `trace` | figure of eight, 0.18 × 0.085 m | Same as circle with a lemniscate path, scaled to fit | Medium |
| `rot` | horizontal arc radius 0.25 m about the elbow | Robot-led arc, scaled radius ≤ 0.10 m | Medium |

## Not on the robot this weekend (show in the app as "coming soon", or as animation only)

| App id | Why not |
|---|---|
| `lift` | Vertical arc of about 0.5 m: outside the workspace and against gravity with a person's arm |
| `knee`, `kneebend`, `legtest` (fig `kneehold`) | Need a shin cuff end effector and a leg set-up; not built, and moving a leg needs its own safety case |

## Demo plan for the pitch

Use one plan the robot can do end to end. Proposal: a "Stroke, arm recovery" plan of `reach` → `push` → `armtest` (add `pull` if the reversed start works). In the app, `PLANS` gets a demo plan with exactly these ids, and the other exercises are shown but not started on the robot.

## Wiring (who builds what)

- **software/ (Shiv):** exercise presets in the engine: `reach`, `push`, `pull`, `armtest` (isometric), each a small config over the existing controller; tests on SimArm. Robot-led `circle`/`trace` only after the MUST four work on the real arm.
- **server/ (Shyan):** `POST /api/session/start` accepts `exercise` (one of the ids above) plus optional reps; returns 422 for ids not live on the robot; `rep` messages and `/api/state` carry `exercise`. Stored in `sessions.exercise`. Update `server/API.md`.
- **demo/ (Mat, Gio):** the app's exercise screen calls the laptop server (`/api/session/start` with the exercise id, live reps from `/ws/live`, `/api/session/stop` at the end) when it is on the station network; the measured values (reach cm, peak N, contribution) replace `stepOf()` demo values. Exercises not live on the robot are labelled as demo animation.
- **robot/ (Kian):** start pose and reach axis for Layout B (reach along world y), the far-end pose for `pull`, and an isometric hold check in the safety tests.
