# Tuning: stiffness and speed values (package K3)

Owner: Kian. **Status 15 Nov: recommendations from the 14 Nov motion test only. Nothing here
has been measured with the handle mounted or with a person holding it.** Section 4 lists what to
measure on the arm; section 5 is where those numbers go.

## 1. What was measured (context/MOTION_TEST.md, tool `Flange`, nothing mounted)

| Measurement | Value | What it tells us |
|---|---|---|
| Hold at nominal stiffness (10000 N/m), 5 s | drift 0.15 mm | The arm holds still; `home()` at nominal stiffness is accurate. |
| 2 cm move at 600 N/m, 0.03 m/s | stopped 7.4 mm short | 600 N/m x 7.4 mm = **about 4.5 N of friction and model error**. Below that force the arm does not move. |
| 4 min motion at 2000 N/m, up to 0.10 m/s | mean lag 15 mm, max 28 mm | Moving costs force on top of friction (the arm's own damping). The lag grows as stiffness falls. |
| Empty force reading, three poses | 1.7 N, 0.7 N, 3.2 N | The estimate moves 1 to 3 N with pose. No wrist sensor: it depends on the tool mass and CoM. |
| Force noise at rest | under 0.14 N peak to peak | Noise is not the problem; pose-dependent offset is. |
| Peak speed in the 4 min run | 0.106 m/s, no trips | |

Not measured yet: stiffness-call latency, drag on a free axis, anything with a hand on the handle.

## 2. The one number that drives everything: 4.5 N of friction

A spring of stiffness K stops pulling the handle when it is within `4.5 / K` of its target:

| Stiffness | Dead band (handle stops this far from the target) | Largest pull (K x 5 cm lead) |
|---|---|---|
| 100 N/m | 4.5 cm | 5 N: about equal to friction, the arm barely moves |
| 180 N/m | 2.5 cm | 9 N |
| 300 N/m | 1.5 cm | 15 N |
| 400 N/m | 1.1 cm | 20 N |
| 500 N/m | 0.9 cm | 25 N |
| 600 N/m (`k_max`) | 0.75 cm | 30 N |

Consequences:

- **Assistance is dead at low dial values.** Assist stiffness is `dial x K_ASSIST`. At dial 0.25
  the pull is at most 5 N, which friction eats. Real help starts at about dial 0.4 (8 N).
- **A released handle on the resistance side stops short of the start**: 1.5 cm at 300 N/m,
  2.5 cm at dial -0.6 (180 N/m). The engine's "back at the start" window is 2 cm, so at
  dial -0.6 an empty handle will not re-arm by itself. With a hand on it this does not matter.
- **What the person feels in resistance is the band plus friction**: about 15 + 4.5 = 20 N going
  out at dial -1, and 15 - 4.5 = 10 N pulling them back.
- The 1.5 cm path-error success limit and the 2 cm start window are close to the dead bands.

## 2b. Found on the arm, 15 Nov: stiffness values act along the tool axes

`SetCartesianImpedance` applies the three translational stiffness values along the TOOL (TCP) axes, not the base axes.
Every per-axis number in this file was written as if they were base axes.

| | Along the reach (base x) | Across (base y) | Up (base z) |
|---|---|---|---|
| Commanded as (200, 500, 500), meant as | 200 | 500 | 500 |
| What the arm had, by tool-frame arithmetic at the start pose | 489 | 211 | 500 |
| Measured along the push, 12 held points | 480 to 500 | not measured | not measured |
| With the helper: `arm.reach_stiffness(200, 500).k` = (500, 189, 500) | 200 | 489 | 500 |

- The start-pose orientation puts tool y 11 degrees from base x. The helper puts the reach value on that tool
  axis and corrects it for the angle: (k_reach - k_across x (1 - w)) / w, with w = cos² of the angle (0.965),
  clipped to 20 to 600 N/m. It is the rule `software/simple.py` uses, and it reports the angle.
- With the correction the wall across the reach is 489 N/m, not 500 (the 11 degrees again), and a push along
  the reach is answered with a small sideways force as well (cross term, about 6 % of the difference).
- A reach axis cannot be made fully free while the walls are on: the lowest it gets at this pose is about
  37 N/m (the 20 N/m floor plus 3.5 % of the wall). Over 30 cm that is 11 N. For `pull`'s set-up phase the
  handle has to be turned square to the reach, or the walls lowered.
- **Until `software/engine.py` uses the helper, its reach and wall stiffness are on the wrong axes on the real
  arm:** `K_ASSIST`, `K_RESIST` and the dial act across the reach, and `K_WALL` (500) acts along it. The
  recommendations in section 3 describe what was intended, not what that engine does on the arm today.
- Also seen in the same set (band at about 490 N/m): the reading rose with hand speed, 26.9 N under 0.10 m/s
  and 38.1 N at 0.10 to 0.15 m/s (7 samples). Whether that stays at the right stiffness is not known.
- Mounting the handle or changing the start pose changes the orientation: check `reach_stiffness().angle_deg`
  again. Above about 20 degrees the single-axis correction is poor (it clips at 45).

## 3. Recommended values

Hard limits in `robot/arm.py` are not changed (and never loosened). Engine constants live in
`software/controller.py` and `software/engine.py`; changing them is Shiv's and Shyan's call,
with a DECISIONS.md line.

| Name | Now | Recommend | Reason |
|---|---|---|---|
| `K_ASSIST` | 400 N/m | **keep 400** | 20 N at full lead: 4.5 N of friction, about 9 N of damping at 0.15 m/s (estimate, see below) and a few N left to carry a limp arm. 600 would give 30 N, right at the contact cap, with no margin. Lower than 300 and the arm cannot carry anything. |
| `K_RESIST` | 300 N/m | **keep 300** | 15 N band, about 20 N felt with friction. Enough to see on the force bar, half of the 40 N trip. At dial -0.6 (180 N/m, 9 N) the band is only twice the friction: for `push` and `pull` prefer dial -0.8 to -1.0 if the actor finds it comfortable. |
| `K_WALL` | 500 N/m | **keep 500** | 0.9 cm dead band and 1.6 cm of sag under an 8 N limb (already removed from the path error). 600 is the hard cap and would gain 2 mm. 300 leaves a 1.5 cm dead band, as wide as the success limit. |
| `K_HOLD` (`Limits.k_hold`) | 300 N/m | **keep 300** | Soft enough that a 13 cm push is needed for 40 N, stiff enough to hold the handle within 1.5 cm. It is also what a trip and Ctrl+C fall back to. |
| Isometric (`armtest`) | `k_max` 600 on the reach axis | **keep, and cap the push at about 25 N** | 600 N/m is the hard cap. 30 N moves the handle 5 cm and is where the spring gives way (`robot/SAFETY.md` finding 2). |
| `max_linear_vel` | 0.15 m/s | **keep 0.15** | The 0.30 m reach in 4 s peaks at 0.14 m/s, just inside. Never raised. |
| `max_linear_acc` | 0.5 m/s² | keep | |
| `trip_speed` / `trip_force` | 0.40 m/s / 40 N | keep | 2.7x the commanded speed; 10 N above the largest spring pull. |
| Reference time `T_OUT_S` / `T_BACK_S` | 4.0 s | **4.0 s; go to 5.0 s if the arm lags at mid-reach** | At 4 s the reference peaks at 0.14 m/s against a 0.15 m/s cap, so any lag cannot be caught up. 5 s peaks at 0.11 m/s. |
| `F_PRESENT` | 1.5 N | **decide after measurement 5** | The empty reading moved up to 2.5 N between poses on 14 Nov. If it still moves more than 1 N along the reach with `RehabHandle`, an empty handle will look occupied; then use (largest change + 1 N). |
| `MAX_BASELINE_N` | 3.0 N | keep, and fix the tool instead | Target under 2 N at the start pose (`robot/tool_handle.md`). |
| Resist rescue ramp step | 0.1 s | **decide after measurement 1** | Assumes a stiffness call takes under 100 ms. |

Estimate behind the "9 N of damping" line (not measured): the 2000 N/m run lagged 15 mm at
0.10 m/s, so 30 N in total, of which 4.5 N is friction. If the arm's damping scales with the
square root of stiffness (constant damping ratio), at 400 N/m and 0.15 m/s it is about
25.5 x sqrt(400/2000) x 1.5 = 17 N at most, and about 9 N if half of the lag was the speed
ramp. Either way the 20 N assist pull has little to spare; measurement 3 settles it.

## 4. To measure on the arm (with `RehabHandle` active, after the safety checks pass)

`python robot/tune.py` walks through these (each step waits for Enter; `--sim` for a dry run).

| # | Measurement | How | Decides |
|---|---|---|---|
| 1 | **Stiffness-call latency** | 50 `SetCartesianImpedance` calls while holding, median and max | Resist rescue ramp step (0.1 s now); whether stiffness changes mid-rep are safe |
| 2 | **Empty force along the reach** | Empty handle, arm moves itself along the reach line at 5 cm/s, force read at 0, 10, 20, 28 cm | `F_PRESENT`; whether the hands-off rule can work at all |
| 3 | **Drag on a free axis** | Reach axis at 0 N/m, a person slides the handle at about 0.1 and 0.2 m/s; mean force along the axis | Is "transparent" really light (under 5 N)? If not, never show dial 0 as "free" (MASTER_PLAN R3) |
| 4 | **Wall feel at 300, 500, 600 N/m** | Push sideways 2 cm at each; measured N/m, return error, and what it feels like | `K_WALL` |
| 5 | **Relaxed arm versus empty handle** | Force with a relaxed arm resting on the handle, still and while carried | `F_PRESENT`: say plainly if they cannot be told apart |
| 6 | **Assist feel at 200, 400, 600 N/m** | Carried reach with a relaxed arm; speed reached, lag, any vibration | `K_ASSIST`, `T_OUT_S` |

**Wall feel at 800 N/m cannot be measured**: `k_max` is 600 N/m and `arm.py` clamps anything
above it. Testing 800 would mean loosening a safety limit, which we do not do. The top point is 600.

## 5. Measured on the arm

Not measured yet. Fill in from `robot/results/tune_<date>_arm.json`.

| # | Measurement | Result | Date, who |
|---|---|---|---|
| 0 | Stiffness frame: (200, 500, 500) commanded, stiffness along base x from 12 held points | 480 to 500 N/m (489 by tool-frame arithmetic): the values act along the tool axes | 15 Nov, Shyan (hand-on Push, tool `Flange`) |
| 1 | Stiffness-call latency (median / max of 50) | | |
| 2 | Empty force at 0 / 10 / 20 / 28 cm along the reach | | |
| 3 | Free-axis drag at about 0.1 / 0.2 m/s | | |
| 4 | Wall: measured N/m and return error at 300 / 500 / 600 | | |
| 5 | Relaxed arm on the handle, still / carried | | |
| 6 | Assist at 200 / 400 / 600: speed, lag, vibration | | |

## 6. Final values

Unchanged from the start values until section 5 is filled in. Any change to a final stiffness
or limit gets a line in `context/DECISIONS.md`.
