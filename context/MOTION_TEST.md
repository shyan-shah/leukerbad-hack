# First motion test on the real arm (Shyan, 2026-11-14, laptop clock 20:29 to 20:47, Swiss time is one hour later)

Status: **in progress.** Stages 0, 1, 2 and a 4-minute video run are done. Stages 3 (soft hold), 4 (free axis)
and 5 (engine dry run) have not been run yet.

`robot/arm.py` drove the real Flexiv Rizon 4 through `flexivrdk==1.7.0` with **no changes to `robot/`**.
Test scripts are on Shyan's laptop in `%TEMP%\flexiv_motion\` (`stages.py`, `demo.py`); they build
`flexivrdk.Robot` themselves and call `Arm._attach(...)` so that `Arm.connect()` (which clears faults and
calls `Enable()`) is never used. The arm comes up already enabled in Auto (Remote) mode.

## Results

| Stage | What | Result | Numbers |
|---|---|---|---|
| 0 | Read-only state, tools, force baseline | done | no fault, operational, IDLE; baseline with `Seat_Assembly_tool` 12.75 N (almost all +z), noise under 0.14 N peak to peak |
| 0a | `Tool.Switch("Flange")` in IDLE | **OK** | force reading 12.72 N to 1.70 N, joints moved 0.00000 rad, no fault. Confirms nothing is mounted. |
| 1 | Hold 5 s at nominal stiffness (10000 N/m), 100 Hz stream | **PASS** | max drift 0.153 mm (limit 2 mm), 97 Hz, force change at most 0.69 N |
| 2 | 2 cm towards the base and back at 0.03 m/s, 600 N/m | **FAIL on the 3 mm criterion, ran safely** | reached 15.7 of 20 mm; tracking error max 14.8 mm, mean 8.3 mm; sideways error max 1.8 mm; ended 7.44 mm from the start; peak speed 0.017 m/s; force change at most 5.15 N |
| video | 4 minutes of continuous translation-only motion, 2000 N/m, up to 0.10 m/s | **completed, no trips** | 241.5 s, 23275 samples; peak measured speed 0.106 m/s; force change at most 6.9 N; tracking error max 28.1 mm, mean 14.9 mm; furthest 191 mm from the start; ended 3.2 mm from the start |
| 3 | Soft hold 300 N/m, hand push | not run yet | |
| 4 | Free axis | not run yet | |
| 5 | Engine dry run, one assisted rep | not run yet | Blocked by the "stages 0 to 4 all pass" rule unless Shyan overrides it (stage 2 missed its criterion). |

Trips in all runs: none. After every run the robot was back in IDLE with no fault and nominal stiffness restored.

The video run went beyond the limits set for the staged test (3 cm, 0.05 m/s, 600 N/m) at Shyan's explicit request:
it stayed inside a box 3 to 11 cm towards the base, 10 cm either side and 2 to 12 cm up from the start, with trips
at 0.30 m/s, 25 N force change and the box edge.

## What the numbers mean

- **RDK calls proven on the real arm with 1.7.0:** `SwitchMode(NRT_CARTESIAN_MOTION_FORCE)`,
  `SetMaxContactWrench`, `SetCartesianImpedance`, `SendCartesianMotionForce` (6-argument form), `Stop`,
  `Tool.Switch`. The `RDK-Professional` licence allows the Cartesian mode: plan A stands, Plan B is not needed.
- **Soft springs do not position the arm precisely.** At 600 N/m the arm stopped 7.4 mm short, which is about
  4.5 N of friction and model error. At 2000 N/m and 0.10 m/s it lagged the moving target by 15 mm on average.
  With `K_ASSIST` 400 N/m and `K_WALL` 500 N/m expect errors of 1 cm or more on an empty handle: the 1.5 cm
  path-error success limit and the 2 cm "near start" window are tight against that.
- **Force baseline moves with pose.** With the `Flange` tool the empty reading was 1.70 N, then 0.67 N, then
  3.2 N at slightly different positions after moves. The engine's 3 N "refuse to start" guard is close to this.
- **Reach direction.** From the start pose, "towards the base" is world `[-0.89, -0.46, 0]`: mostly -x. The
  closest single world axis is **x, negative sign**. A reach away from the body along one base axis is not
  available from this pose; either turn the setup so the reach lies along x, or pick a new start pose.

## Start pose used (tool `Flange`, so TCP = flange)

`tcp_pose = [0.78045, 0.40195, 0.43791, 0.72738, -0.00848, 0.02265, -0.68581]`,
`q = [0.98372, -1.80017, -1.98675, 0.98977, -1.11338, 0.25369, 1.55581]`.
The flange is 0.88 m from the base axis, near the edge of reach. Recommendation: choose a demo start pose
closer in (the arm ran well 3 to 11 cm further in) with the reach along world x, and re-record it once the
handle is mounted and set as the tool.

## For Kian

1. `robot/config.json`: set `"serial": "Rizon4-062157"` (tests used a config copy under `%TEMP%`).
2. `Arm.connect()` calls `ClearFault()` and `Enable()` unconditionally. The arm is already enabled in Auto
   (Remote) mode, so it worked without them. Decide whether `connect()` should skip `Enable()` when
   `operational()` is already True, and add the "already live on power-up" warning to the RUNBOOK.
3. The robot's tool is now `Flange`, not the other team's `Seat_Assembly_tool`. Add our handle as a tool
   (mass, CoM) when it is mounted, then re-read the start pose.
4. `ZeroFTSensor` has not been tried. `ft_sensor_raw` is all zeros (probably no wrist sensor), so test it
   under supervision before relying on `zero_force()`.
5. Tracking at 600 N/m is poor by design; if `home()` needs to be accurate it already uses nominal stiffness, which held to 0.15 mm.

## For Shiv

1. Expect 1 to 1.5 cm position error at `K_ASSIST`/`K_WALL` stiffness from friction alone, and an
   empty-handle force that changes by 1 to 3 N with pose. `MAX_BASELINE_N = 3.0` may refuse starts on the real arm.
2. Reach axis candidate from this pose: x with sign -1 (`reach_axis=0, reach_sign=-1`), but the true
   direction is 27 degrees off the x axis.
