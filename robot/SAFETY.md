# Safety sheet: Flexiv Rizon 4 rehab arm (package K2)

Owner: Kian. Robot `Rizon4-062157`, robot software v3.9.3, flexivrdk 1.7.0.

**Status: NOT SIGNED OFF.** No check below has been run on the real arm yet. Until the
table has an on-arm PASS on every row and the sign-off block is filled in, **nobody holds the
handle** except the technician doing the checks.

## How to run the checks

1. Follow `robot/RUNBOOK.md` section 1 (roles named, e-stop holder in place, arm free: only one
   laptop drives it).
2. The handle is mounted and `RehabHandle` is the active tool (`robot/tool_handle.md`).
   `python robot/read_tool_force.py` reads under about 2 N.
3. `python robot/safety_check.py` (arm venv with flexivrdk 1.7.0). It refuses to start unless
   the robot is fault-free, operational, in IDLE, e-stop released and the tool is `RehabHandle`.
   It never enables the robot or clears a fault.
4. Type `go`. Each step waits for Enter; while it waits the arm is in soft hold.
   **The technician does every hands-on check first.**
5. Any FAIL: the script holds and asks. Default is stop. Nobody holds the handle until the
   cause is fixed and the check is re-run (`--only 7,8` re-runs single checks).
6. Paste the printed table into "Results on the real arm" below and commit the JSON file it
   saved in `robot/results/`.

Dry run without a robot: `python robot/safety_check.py --sim`.

## Results on the real arm

Date: ____________  Run by: ____________  Technician: ____________  Tool: ____________
Result file: `robot/results/safety_check_<date>_arm.json`

| # | Check | Pass criterion | Result | Measured |
|---|---|---|---|---|
| 1 | Empty handle force near 0 with the active tool | mean force under 2 N, nobody touching | not run | |
| 2 | Push direction gives the expected force sign | force along the reach axis has the same sign as the push (over 3 N, over 3 mm) | not run | |
| 3 | Soft hold at K_HOLD | 300 N/m sent; 0.5x to 2x of that measured; returns within 2 cm | not run | |
| 4 | A target outside the box is clamped | asked 20 cm up, sent at most 10 cm, hand stays within 1 cm of the box edge | not run | |
| 5 | A target 20 cm from the hand is clamped to 5 cm | sent target is 5 cm from the hand | not run | |
| 6 | Stiffness 5000 is clamped | 600 N/m sent on every axis | not run | |
| 7 | Pushing past 40 N trips to hold | ends in hold; force never more than 5 N past the trip | not run | |
| 8 | Hand 3 cm outside the box trips | box trip 2 to 3 cm outside a 3 cm test box | not run | |
| 9 | Stopping the command stream trips the watchdog | hold within 0.3 s | not run | |
| 10 | Letting go mid-assist stops the arm | stops within 10 cm of the release | not run | |
| 11 | Letting go in resistance | returns under 0.20 m/s, stops within 3 cm of the start, no overshoot, no trip | not run | |
| 12 | Isometric hold at K_MAX | a push of 20 to 30 N moves the handle at most 5 cm, no trip | not run | |
| 13 | Letting go during pull's set-up phase | coasts under 3 cm, then moves under 5 mm in 2 s | not run | |
| 14 | Ctrl+C leaves the arm in hold | mode hold at 300 N/m, moves under 1 cm in 2 s | not run | |
| 15 | After close() stiffness is back to K_x_nom | `[10000,10000,10000,1500,1500,1500]` sent, then Stop, no fault | not run | |

Peak forces to copy from the run (for the pitch; nobody says a force limit on stage that is not in this table):

| Case | Peak force measured |
|---|---|
| Carried in assist (check 10) | not run |
| Pushing against the band (check 11) | not run |
| Push that tripped the arm (check 7) | not run |

## Dry run on the simulated arm (15 Nov, not evidence about the robot)

`python robot/safety_check.py --sim`, result file `robot/results/safety_check_2026-11-15_1145_sim.json`.
This only shows the script and the clamps/trips shared with `SimArm` work. 13 PASS, 0 FAIL, 2 not
reproducible in the sim.

| # | Sim result | Measured in the sim |
|---|---|---|
| 1 | PASS | 0.00 N |
| 2 | PASS | moved +27 mm along y, force +6.0 N |
| 3 | PASS | 4.1 cm for 9.0 N (220 N/m with overshoot; 300 commanded); back to 0.0 mm |
| 4 | PASS | asked 20 cm; sent at most 10.00 cm; hand rose 10.3 cm |
| 5 | PASS | sent 5.00 cm |
| 6 | PASS | sent 600, 600, 600 |
| 7 | PASS | hold at 34.8 N, by the speed trip, not the force trip (see finding 1) |
| 8 | PASS | tripped 2.1 cm outside the 3 cm test box |
| 9 | PASS | hold after 0.19 s |
| 10 | PASS | 3.2 cm after release, but stopped by the speed trip (the sim has no speed limit) |
| 11 | N/A | the sim has no robot-side speed limit: the released band trips at 0.41 m/s |
| 12 | PASS | 28.0 N moved the handle 4.7 cm |
| 13 | PASS | coasted 2.1 cm, then still |
| 14 | PASS | hold, 300 N/m, 0.0 mm |
| 15 | N/A | the sim has no nominal stiffness |

## What the checks do and do not prove

- **Checks 4, 5, 6, 15 read what `robot/arm.py` actually sent to the robot** (a recorder wrapped
  round the RDK object). flexivrdk 1.7.0 has no getter for the active stiffness, so check 15 is
  "the command was sent and accepted", not a measurement.
- **Check 8 uses a tightened box.** The side box is set to 3 cm for the test (same trip code, never
  looser), so the handle is not pushed 12 cm sideways against the spring. The default 10 cm edge
  itself is not physically reached.
- **Checks 10, 11, 13 use the script's own small copies of the exercise laws**
  (`K_ASSIST` 400, `K_RESIST` 300, `K_WALL` 500, hands-off rule 1.5 N / 0.5 s), because `robot/`
  imports nothing from `software/`. They prove how the ARM behaves when a person lets go under
  those commands. They do not prove the engine's own hands-off rule or its `pull` and `armtest`
  presets (Shyan's E1): **one engine run per exercise with a deliberate let-go is still needed**
  and is not covered by this sheet.
- Check 10 depends on the empty handle reading under 1.5 N above its start-pose baseline all
  along the reach. On 14 Nov the empty reading moved 0.7 to 3.2 N with pose (tool `Flange`).
  If that is still true with the handle, check 10 FAILS with "the handle never read empty",
  and the hands-off rule cannot be relied on until the tool mass/CoM is right.

## Findings from writing the checks (arithmetic and sim, to confirm on the arm)

1. **A hold gives way at stiffness x 5 cm while targets are streaming.** `set_target` always
   clamps the target to 5 cm from the hand, so the spring can never pull harder than
   600 N/m x 0.05 m = 30 N (15 N at K_HOLD). Push harder and the handle follows the push.
   So in check 7 the person feels the handle start to move at about 30 N and the trip comes at
   40 N (force) or 0.40 m/s (speed), whichever is first. Only after `hold()` or a trip is the
   target fixed, and then nothing trips again: 300 N/m x distance.
2. **The isometric test (`armtest`) cannot measure more than about 30 N.** At K_MAX a 30 N push
   already moves the handle 5.0 cm (30 / 600), which is exactly the limit in check 12, and above
   30 N the handle slides and then trips. "No motion beyond about 1 cm" in
   `context/EXERCISE_MAP.md` holds only up to 6 N. Raising `k_max` would be loosening a safety
   limit and is not done. For the demo: the actor pushes gently (under 25 N) and the screen should
   not call the number "maximum strength".
3. **An empty handle released under a 20 N assist pull accelerates fast.** In the sim it reached
   0.48 m/s in under 0.1 s and was stopped by the speed trip, not by the hands-off rule. The real
   arm has its own speed limit (0.15 m/s on every command) and damping; check 10 measures what
   really happens.

## Limits in force

In code (`robot/arm.py` `Limits`; callers cannot override them, and this sheet is void if they are loosened):

| Limit | Value |
|---|---|
| Max stiffness `k_max` | 600 N/m |
| Max target lead `max_lead_m` | 0.05 m (so the spring pulls at most 30 N) |
| Hold stiffness `k_hold` | 300 N/m |
| Commanded speed / acceleration | 0.15 m/s, 0.5 m/s² on every command |
| Speed trip | 0.40 m/s |
| Force trip | 40 N |
| Robot contact cap (`SetMaxContactWrench`) | 30 N, 5 Nm |
| Watchdog | 0.2 s without a target |
| Workspace box | ±0.35 m along the reach, ±0.10 m across, ±0.10 m up/down from the start pose; trip 2 cm outside |

In Flexiv Elements (set by the technician only; not reachable from our code):

| Elements limit | Value set | Set by | Date |
|---|---|---|---|
| TCP speed limit | | | |
| Force / collision limit | | | |
| Safety plane between the arm and the person's torso (position) | | | |
| Other (joint limits, reduced mode) | | | |

## Sign-off

I have done every hands-on check above myself before any team member, the results table is
complete with no FAIL, and the Elements limits above are set.

| | |
|---|---|
| Technician name | |
| Signature / initials | |
| Date and time | |
| Tool active during the checks | |
| Elements limits confirmed (TCP speed, force, safety plane) | |
| Conditions or restrictions (who may hold the handle, which exercises) | |

Team: operator ____________  e-stop holder ____________

Rules that stay in force after sign-off: healthy team members only; e-stop holder in place
whenever the arm is powered (it comes up already enabled); re-run the checks after any change
to `robot/arm.py` limits, the tool, the handle mounting or the start pose.

## Safety events

Append here anything that tripped unexpectedly, faulted, or frightened anyone: date, what
happened, what was done.

| Date | Event | Action |
|---|---|---|
| 14 Nov | "Robot and Control Box are disconnected" in Elements | loose arm cable: power off, reseat both ends, power on (`robot/RUNBOOK.md`) |
| 14 Nov | Wrong tool selected (`Seat_Assembly_tool`, not mounted): 12.6 N false force on an empty flange | switched to `Flange`; our handle gets its own tool `RehabHandle` |
