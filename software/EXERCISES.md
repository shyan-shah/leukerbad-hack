# Robot exercise programmes (E1)

Presets live in `software/exercises.py` (`EXERCISES`, `LIVE`); the engine applies one with
`Engine(..., exercise="<id>", reps=None)`. The app ids are those of `context/EXERCISE_MAP.md`.
All numbers are team-chosen starting values, not clinical prescriptions. Everything below was
tested on `SimArm` only (`software/tests/test_exercises.py`, 39 tests, reach along x and along y as in Layout B; `software/tests/test_real_arm_effects.py`, 180 tests with the real arm's friction and force-reading errors simulated); nothing here has run on the real arm yet.

`LIVE = ("reach", "push", "pull", "armtest")`. `circle` is implemented but not live.

## Engine call

```python
from software.engine import Engine
eng = Engine(arm=arm, session_id=sid, patient_id=pid, simulated=sim,
             reach_axis=arm.reach_axis, reach_sign=cfg_sign,      # the configured reach direction
             on_sample=..., on_rep=...,
             exercise="push",        # "reach" (default) | "push" | "pull" | "armtest" | "circle"
             reps=None)              # see "Reps" below
eng.start(); ...; eng.stop()
```

- **`exercise`** unknown id: `ValueError` listing the known ids. Default `"reach"` is today's behaviour, unchanged.
- **`reach_m`** given: overrides the preset's length (for a short test run). Not given: the preset's.
- **`dial`, `auto`**: for `reach` they are the caller's, as before. For every other preset `auto` is the preset's, and `dial` is used only if it is on the preset's side (`push`/`pull` accept a negative dial, anything else falls back to -0.6). So the server can keep sending its default `dial 1.0, auto true`.
- **`reach_sign`** is always the configured reach direction; the preset's `direction` is applied on top (`pull` reverses it).
- **Reps.** `reps=N`: no new rep is armed after N. `reps=None`: `reach`, `push` and `pull` keep running until `stop()` (as today) and the preset's `default_reps` is only reported; `armtest` and `circle` always stop after their own count.
- **`snapshot()`** adds `exercise`, `kind`, `reps_target`, `done` (`rep_count >= reps_target`).
- **Not in the contract:** `Sample` and `RepResult` have no exercise field (the contract is in `server/`), so the exercise is in `snapshot()` only. `Engine.stop()` returns `SessionSummary.exercise` = the preset id (`"reach_line"` for `reach`, unchanged).
- New values in existing fields: `Sample.phase` can be `"setup"`; `RepResult.mode` can be `"isometric"` or `"guided"`.

## The programmes

| id | kind | line | dial | auto | default reps | notes |
|---|---|---|---|---|---|---|
| `reach` | assist | 0.30 m from the start pose, configured direction | +1.0 | yes | 10 | today's engine |
| `push` | resist | 0.28 m, same line | -0.6 | no | 10 | band pulls back to the start |
| `pull` | resist | 0.28 m, reversed: starts at the far end, "out" is towards the patient | -0.6 | no | 10 | setup phase first |
| `armtest` | test | none (handle held at the start pose) | 0 | no | 3 tries | 3 s push, 5 s rest |
| `circle` | guided | circle radius 0.08 m, plane of the reach axis and world z | 0 | no | 8 circles | 6 s per circle, 300 N/m on all axes, not live |

### reach
Section 4.2 of the master plan, unchanged: idle (soft hold) → out → back, hands-off rule, stall rescue, auto dial. Measured per rep on the out phase: duration, ROM, path error, SPARC, peak and mean force, contribution.

### push
Same state machine and metrics on the resist side: the target sits 5 cm behind the hand towards the start, along-path stiffness `0.6 * K_RESIST` = 180 N/m (about 9 N of band). No auto dial. Sim, strong patient: 3 of 3 reps completed, peak force 12.6 N, ROM 0.253 m.

### pull
The line is the push line run backwards: path start = start pose + 0.28 m along the configured reach (the far end), path end = the start pose.
- **`setup`** (`Sample.phase == "setup"`, dial reported as 0): transparent along the line, walls on the other two axes, target on the hand. The patient moves the handle out to the far end. The arm never drives it there in setup: with an empty handle nothing moves (tested for 8 s).
- **One exception since the release rule:** if the patient lets go during a pull rep, the handle is walked back to the far end (the path start) at 2 cm/s, away from the patient. See "Release" below.
- When the hand has been within 2 cm of the far end for 1 s: `idle` (soft hold at the far end), then reps as usual. "out" is towards the patient; the band pulls back towards the far end in both phases.
- Setup is entered only at `start()`, and only if the hand is not already at the far end.
- Since 15 Nov every exercise has this setup, not only pull: see "Starting away from the path start" below.
- Sim, strong patient: setup took 3.5 s, then 3 of 3 reps completed, peak 12.6 N.

### armtest (isometric)
- `idle`: soft hold until a hand has been on the handle at the start for 1 s. Then 3 tries: `out` = push for 3 s, `back` = rest for 5 s. After the last try: `idle`, `done`.
- During a push the target is the start pose, the reach axis is at `arm.limits.k_max` (600 N/m, the arm's own clamp) and the other axes at `K_WALL`. That stiffness stays on from the first try to the last.
- One `RepResult` per try: `mode "isometric"`, `peak_force_n` and `mean_force_n` are the force **along the reach axis in the push direction**, relative to the engine's force baseline; `rom_m` is the largest displacement; `contribution` 1.0; `completed` if the peak is over 5 N; `duration_s` the push time; `sparc` 0.
- A push that moves the handle more than 5 cm ends the try early (it is still recorded). With 600 N/m that is 30 N, the same as the arm's contact limit, so **readings top out at about 30 N**.
- **Letting go mid-push** ends the try (recorded with whatever peak it reached) and releases the spring gently: see "Release" below.
- **Rest is not a fixed target.** When a push ends the target is put on the hand and walked back to the start at 2 cm/s. With the target left on the start pose, the simulated patient relaxing from 20 N let the spring snap the handle back at 0.46 m/s, which tripped the speed limit and ended the session.
- Sim: strength 0.8 gives 20.1 N peak (patient's cap 20 N), 13.0 N mean, 3.5 cm displacement; strength 1.0 gives 25.1 N and 4.3 cm.

### circle (stretch, not live)
Robot-led: after the usual 1 s with a hand on the handle at the start, the target moves round the circle (start pose = nearest point, centre one radius along the reach) at 6 s per circle with 300 N/m on all three axes. No assist-as-needed and no tunnel. The target waits while the hand is more than 5 cm from it. One `RepResult` per circle (`mode "guided"`, `rom_m` = extent along the reach, path error = distance from the circle). Phase is `out` for the first half and `back` for the second.
- Sim, passive (limp) patient: 8 of 8 circles, 6.0 s each. The limb's 8 N sags the handle a constant 2.7 cm at 300 N/m; with that constant sag removed (the same rule as the line's path error) the hand stays within 1.5 cm of the circle. Without removing it the hand rides 2.7 cm below the circle, so "within 2 cm" holds only in that sense.

## Hands off

| kind | what happens when the person lets go | tested |
|---|---|---|
| assist (`reach`) | hands-off rule: the rep ends, the target is latched, the hand stops within 8 cm | yes |
| resist (`push`, `pull`, and `reach` at a negative dial) | release (below): the rep ends as not completed, no trip, the handle walks back to the path start at 2 cm/s, the session goes on | yes, let go at 25%, 50% and 90% of the reach |
| test (`armtest`) | release (below): the try ends and is recorded (completed if its peak was over 5 N), no trip, the handle walks back to the start pose, the remaining tries wait for a hand at the start | yes, let go at 25%, 50% and 90% of the push |
| guided (`circle`) | the circle ends as not completed, phase `idle`, the target stops | yes |
| `pull` setup | nothing moves | yes |
| any, session started with the handle away from its path start (e.g. `armtest`, `reach` or `push` after `pull`) | `setup` phase: the reach axis is free, the walls are on, nothing drives the handle. The person brings it to the start; a try, rep or circle starts only after 1 s there | yes, each of `armtest`, `reach`, `push`, `circle` started after `pull`, empty and held |

### Release: letting go of a loaded spring (resist side and armtest)

The band (up to 15 N) and the test hold (up to 30 N) are stretched springs. Before 15 Nov a let-go threw the empty handle back at 0.40 to 0.46 m/s in the sim and the speed trip ended the session. Now:

1. **Detect.** Let go = the handle is unoccupied (the usual 0.5 s rule), or, on a single tick, the force on the handle is under `F_PRESENT` (1.5 N) while the commanded spring pull along the reach axis is over 1 N. The second test acts within one 10 ms tick; waiting 0.5 s would be too late. A person still holding on, even one moving back with the band, is not a let-go.
2. **Target on the hand at once** (the exact hand position, so the wall springs let go of the limb's weight too): no spring force from that tick.
3. **Ramp** the reach-axis stiffness to zero over 1 s in 0.1 s steps (the stall-rescue ramp's constants); the walls stay on.
4. **Walk back.** Soft hold (300 N/m on all axes), target walked to the path start at 2 cm/s. For `pull` the path start is the far end, away from the patient. A hand back on the handle stops the walk and the ordinary idle rule takes over.
5. `idle` at the start; the next rep or try needs a hand on the handle there for 1 s, as always.

`Engine.phase` is `"release"` during steps 2 to 4; Samples are labelled `"idle"`.

Sim results (`test_let_go_releases_gently_no_trip_and_the_session_goes_on`, 9 cases):

| exercise | let go at | speed when let go | peak speed after | 0.3 s later |
|---|---|---|---|---|
| push, pull | 25% | 0.18 m/s | 0.18 m/s | under 0.08 m/s |
| push, pull | 50% | 0.23 m/s | 0.23 m/s | under 0.10 m/s |
| push, pull | 90% | 0.15 m/s | 0.15 m/s | under 0.07 m/s |
| armtest (25 N push) | 25%, 50%, 90% | under 0.05 m/s | under 0.05 m/s | 0.03 m/s |

No trip in any case, the handle ends on the path start, and reps or tries resume when the patient takes the handle again. Let go in the back phase (0.5, 1.5, 2.5 s in): released at up to 0.12 m/s, never above 0.15 m/s.

**Two limits on "never above 0.15 m/s":**
- **The patient's own speed.** In push and pull the simulated patient is itself moving at 0.15 to 0.23 m/s when it lets go in the out phase. The arm adds nothing to that (peak after = speed at release), and the handle is under 0.15 m/s within 0.3 s.
- **One tick of delay.** The table above has the engine seeing the let-go before the spring has acted. In a real loop the spring gets up to one 10 ms tick first (`test_let_go_seen_one_tick_late_measured_limits`):

| case, detection one tick (10 ms) late | peak speed |
|---|---|
| armtest, 20 N held | 0.14 m/s |
| armtest, 25 N held | **0.17 m/s** |
| push, let go 1.5 s into the back phase (moving at 0.12 m/s) | **0.175 m/s** |
| push, let go 0.5 s into the back phase | 0.06 m/s |
| armtest, 25 N held, two ticks late | 0.32 m/s (still under the 0.40 m/s trip) |

So the 0.15 m/s target is met when the let-go is seen at once and missed by about 0.02 m/s for the strongest loads when it is seen one tick late; in every case there is no trip and under 0.15 m/s within 0.3 s. This is the limit of a 100 Hz loop on the sim's 1.5 kg handle (25 N for 10 ms is 0.17 m/s), not a tuning value. The real arm is heavier and damped, so expect less, but it is not measured.

**Not proven on the real arm.** Since 15 Nov the let-go tests no longer need the empty handle to read under 1.5 N (see "Telling a hand from an empty handle" below), but they rest on two things only the arm can show: that the reading of a moving empty handle lies along its motion, and that a relaxed hand reads more than 4.5 N.

## Starting away from the path start (setup for every exercise)

`pull` ends with the handle at the far end. Before 15 Nov the next session started in idle there; the simulated patient hauled the handle 28 cm to the start at 0.45 m/s, the speed trip fired within 0.03 s, and the session sat in hold with no reps until it was stopped.

Now `start()` puts **any** exercise into `setup` when the handle is more than 3 cm (along the reach) from that exercise's path start:

- `Sample.phase == "setup"`, dial reported as 0, `rep_idx` -1. Reach axis free (0 N/m), walls at `K_WALL`, target beside the hand on the path line. The target is not clamped to the path segment: a handle left beyond a short path's end is not pulled to it (clamped, it tripped the speed limit in 40 ms).
- The arm never moves the handle in setup. An empty handle stays where it is, for as long as it takes.
- Setup ends when the hand has been within 3 cm of the path start for 1 s; then `idle`, and the exercise runs as usual.
- Sim: after a pull, `armtest`, `reach` and `push` are brought back in about 3.4 s (peak 0.2 m/s) and then run all their reps; through the server API too (pull then armtest on one arm).
- **A person who moves the handle back faster than 0.40 m/s still trips the arm.** That is the speed limit doing its job; the session then needs a stop and a new start.
- **For the screens (server/, not changed here):** the patient screen and the app show "Move the handle to the far end" for every `setup` sample. For reach, push and armtest the right text is "Bring the handle back to the start".

## Telling a hand from an empty handle (15 Nov)

The arm has no wrist sensor. On 14 Nov the reading with nothing on the flange changed by up to 3 N with pose (0.7 to 3.2 N) and read 3 to 7 N while the arm moved. On 15 Nov (Shyan, `server/hw/results/drift_check_2026-11-15.json`: zeroed at the start pose, 0.30 m along the reach at 5 cm/s and nominal stiffness) it read 0.04 to 2.76 N standing (relative to the zero at the start pose), mostly sideways and down (across the reach), at most 3.39 N while moving, and 0.95 N back at the start. The largest difference between any two standing readings was 3.30 N (the same spot, 20 cm out, on the way out and on the way back). That is what counts when a session starts somewhere else on the reach: it is above `EMPTY_REST_N` (3.0) and leaves 1.2 N of the 4.5 N threshold, not 1.5 N. With the old rule (over 1.5 N = a hand) a moving empty handle counts as held: in the sim an empty handle was carried 12 to 18 cm on the assist side, a let-go in push tripped the speed limit, and a pull never left setup.

| Constant (`software/engine.py`) | Value | Meaning |
|---|---|---|
| `EMPTY_REST_N` | 3.0 N | largest change of the empty reading with pose, at rest |
| `EMPTY_MOVING_N` | 7.0 N | largest empty reading caused by motion |
| `F_PRESENT` | 1.5 N | margin on top (unchanged) |
| `HAND_ON_N` | 4.5 N | `F_PRESENT + EMPTY_REST_N`: hand force above this = a hand is on the handle |
| `V_MOVING` | 0.002 m/s | faster than this the handle counts as moving |
| `MAX_BASELINE_N` | 6.0 N (was 3.0) | `start()` refuses above this empty reading |
| `NEAR_START_M` | 0.03 m (was 0.02) | "at the start" for arming a rep, ending setup, and ending a rep whose return has stopped |
| `HOLD_START_M` | 0.02 m | inside this the idle hold pulls a held handle onto the start point; a moving return ends here |

- **Hand force** = the baseline-relative reading with up to 7 N taken off along the direction the handle is moving in (either sign, any direction, whenever it moves faster than `V_MOVING`). A hand is on the handle when that is over 4.5 N for both the raw and the 50 ms-smoothed reading. Occupied = a hand within the last 0.5 s, as before.
- **The one-tick let-go test** (resist side and armtest) uses the same 4.5 N but takes the 7 N off the reach-axis part only, and only while the handle moves along the reach. Otherwise a limb resting on a handle that is settling up or down (its weight then lies along the motion) would be read as a let-go.
- **Every unknown is decided towards "empty".** A missed hand ends a rep; an empty handle taken for a hand would be driven.
- **Baseline** follows the reading only while the handle is idle, empty, not moving and reading within 1.5 N of the baseline. So the 3 to 7 N of a moving empty handle is never absorbed, and neither is a hand resting lightly on the handle (a 4 N hand, too light to count, was absorbed within a minute before this gate; the empty handle would then have read as held). Slow drift stays inside 1.5 N and is still followed.
- **Start refusal** at 6 N: above the real empty readings (3.2 N, plus up to 3 N with pose), below a limb resting on the handle (8 N in the sim) and the wrong tool (12 to 13 N).
- `circle` (not live) moves the handle up and down by design, so it keeps the reach-only allowance; its hands-off rule is not robust to the moving reading.

**What a person has to do to count as "on the handle":** rest or press with more than 4.5 N in any direction while still, and while moving with more than 4.5 N across the motion or more than 11.5 N along it. The simulated limb rests 8 N on the handle (5.7 N for a strong patient who half-carries their own arm), so the sim passes with 1.2 to 3.5 N to spare. **Whether a real relaxed hand reads over 4.5 N is not known.**

### Measured in the sim with the effects on (`software/tests/test_real_arm_effects.py`, 180 tests)

SimArm options, all off by default: `empty_force_pose_n_per_m`, `empty_force_moving_n` (with `empty_force_moving_dir`: `"against"` the motion, `"with"` it, or a fixed direction), `friction_n`. "Real" below = 3 N over the length of the reach, 3 to 7 N against the motion, 4.5 N friction; "noise" adds 0.3 N sensor noise and 200 ms stiffness latency. A sixth set ("real-across": the pose reading pointing sideways and down, as measured on 15 Nov, plus noise) gives the same results as "Real + noise" in every row.

| Check | Effects off | Readings only (no friction) | Friction only | Real | Real + noise |
|---|---|---|---|---|---|
| Empty handle, 20 s, each of the 4 exercises | no rep, no motion | same | same | same | same |
| Assist side: travel after a let-go, limp arm carried at 0.13 m/s, let go at 30% | 7.6 cm | 7.6 cm | 7.3 cm | 7.3 cm | 7.3 cm |
| same, let go at 60% | 6.9 cm | 6.9 cm | 6.2 cm | 6.2 cm | 6.2 cm |
| same, strong patient at 50% | 3.7 cm | 3.7 cm | 0.8 cm | 0.8 cm | 0.8 cm |
| Time from let-go to the rep ending | 0.5 s | 0.5 s | 0.5 s | 0.5 s | 0.5 s |
| push, pull, armtest: let go at 25, 50, 90% | no trip, seen on the first tick, session goes on | same | same | same | same |
| Handle after the walk back | on the start | on the start | 1.4 cm short | 1.4 cm short | 1.4 cm short |
| Sessions (reach 1.0 / 0.3 / limp, push 1.0 / 0.5, pull, armtest 0.8 / 0.3) | all reps completed | same | same | same | same |

- **Release detection is not slower.** The assist-side travel is the same 7.6 cm as before the change without friction (the bound is 8 cm, so the margin is still 4 mm), and friction shortens it. Shyan's nine resist-side cases give the same speeds as his table.
- **Friction lag.** A released handle stops up to 1.5 cm short at 300 N/m and 2.5 cm at dial -0.6. A return that has stopped inside 3 cm now ends the rep (before, only 2 cm did, and a rep that stopped at 2.5 cm waited for the 10 s timeout). While the handle is still moving the 2 cm window is unchanged. Mean path error stays under 0.2 cm in the sim (limit 1.5 cm) and the measured range is 25 to 27 cm.
- **armtest:** the spring is walked back after the last try too. Before, the last try went straight to idle; with 200 ms stiffness latency the 600 N/m spring was still on and snapped the relaxing arm back at 0.43 m/s (trip).
- Random soak, one arm, 40 sessions of the four exercises, random strength, offset, drift, noise, latency and reading direction: 0 trips, 0 refused starts, 134 of 137 reps completed.

### Limits (say these out loud)

1. **Direction of the moving reading.** At 5 cm/s the real reading stayed under 3.4 N in total (15 Nov), which is under the 4.5 N threshold whatever its direction, so at that speed the rule holds on the real numbers. At rep speed (14 cm/s) it has not been measured; 14 Nov saw up to 7 N at 10 cm/s. The rule assumes the part above 4.5 N lies along the motion (either sign). If it points **across** the motion, an empty handle reads as held: in the sim it was carried 19 cm (limit 8 cm) and a let-go in push tripped the speed limit, as with the old rule (`test_known_limit_a_moving_reading_across_the_motion_defeats_the_rule`). No threshold fixes that without also dropping real hands; it would need a calibration sweep of the empty arm or a better tool model.
2. **A reading with the motion** (the arm appears to be pushed along): reach, push and pull behave the same (7.6 cm), but with no friction in the sim, armtest tries by a strong simulated patient were cut short as let-gos (their limb reads 5.7 N, and the reading jitters as the handle settles); with friction on they completed. Rep metrics are also inflated: a limp arm scored 0.86 contribution and the auto dial fell to +0.4.
3. **Very weak patients and friction.** Someone who cannot push 4.5 N cannot slide the handle when the reach axis is free: they cannot do setup, push or pull (sim: strength under 0.2 stalls). The operator moves the handle for them, or they do `reach` only.
4. **Force numbers include the arm's own reading error**, up to 7 N while moving. Peak force in push and pull is that much uncertain; armtest is read near standstill, so it is off by the pose change only (up to 3 N).

### To measure on the real arm before a person holds the handle (Kian)

1. Empty handle (`RehabHandle` tool), arm moving itself along the reach at 5 cm/s **and at rep speed (14 cm/s)**, both directions: the reading per axis. How much lies along the motion, how much across? Which sign?
2. Empty handle at rest at 0, 10, 20, 28 cm, approached from each side: the reading per axis. Is the largest difference between any two readings (the same spot from both sides included) under 3 N? On 15 Nov with the bare flange it was 3.3 N.
3. A relaxed arm resting on the handle, still and while carried: the reading per axis. Is it over 4.5 N, and in which direction?
4. Assist side, dial +1, let go mid-reach: how far does the handle travel? (under 8 cm)
5. push at dial -0.6 and armtest at 15 to 20 N: let go. No trip, handle walks back? How far short of the start does it stop? (1.5 cm expected)
6. Friction: with the reach axis free, the force needed to start the handle moving (4.5 N expected).
7. Speed noise: 5 s of `tcp_vel` with the arm standing still. `V_MOVING` is 2 mm/s (from the sim); if the standing arm reads more than that, say so.
8. push with a normal grip, letting the band bring the hand back: is the rep cut short as a let-go? (It must not be.)

If 1 shows more than about 2 N across the motion, or 3 shows under 4.5 N, do not run the assist side with a person until the rule is changed.

## Simulated patient hooks (`software/sim_arm.py`)

`SimArm.reach_origin` (where the patient's reach starts), `SimArm.auto_cue` and `SimArm.cue("out" | "rest" | "back")`. The engine sets them in `start()`; for `pull` and `armtest` it cues the patient itself, for `reach`, `push` and `circle` the patient follows the stiffness change as before. Defaults reproduce the old behaviour.

## Arming, idle and go() (15 Nov, 16:45; supersedes the "1 s with a hand at the start" rule above for reach, push, pull and armtest)

Sim only (`software/tests/test_arming.py`); not run on the real arm.

- **Idle near the start (within 5 cm, 3D):** the idle target walks to the start at 2 cm/s in the 300 N/m hold; when it is there and the handle is within 3 cm, the hold stiffens to `k_max` (600 N/m) on all three axes over 1.5 s in 0.25 s steps (at once if the handle is within 5 mm of the start).
- **Arming:** in that firm hold, a baseline-relative force (50 ms smoothed, any direction) over 4.5 N and at most 25 N, with the handle slower than 0.05 m/s, for 0.6 s. Ticks that fail count the 0.6 s back down. The circle keeps the old rule.
- **`snapshot()["arming"]`** = `{"progress": 0..1, "reason": ...}`; reasons "press gently", "hold still", "too far from start" (empty and away, being walked back), "pushing too hard", "return to start" (hand on and away, or the target still walking in).
- **Idle away from the start:** hand on = soft hold where it is, the target follows the hand only towards the start. Empty = walked back to the start at 2 cm/s (also after an assist-side let-go).
- **`Engine.go()`:** 3 s later the next rep is armed if the handle is within 5 cm of the start and the force is between 2 and 25 N.
- **`Engine.resume()`:** after a trip, home and prepare: compliance restarts and the session keeps its reps. **`stop()`** records a rep in progress as not completed.
- **Calibration:** `software/strength_model.py` exists (fraction 0.5, bounds 0.3 to 0.8, step 0.05 per set; resistance = fraction x comfort force, 3 N to the maximum). The engine's calibrate phase does not: `snapshot()["calibration"]["status"]` is always "skipped" and push and pull use the preset dial.
- Measured: grips of 6, 10 and 18 N arm in 0.74 to 1.00 s and complete the first rep; an empty handle did not arm in 20 s; after go() an empty handle moved under 8 cm. Limit: a hand pushing about 15 N or more while the hold is still stiffening after a rep slides past 5 cm and has to come back.

## Update 15 Nov, 19:00 (supersedes the lines above where they differ)

Sim only: `test_arming.py`, `test_calibration.py`, `test_rep_audit.py`.

- **Firm hold:** entered whenever the idle target is on the start and the handle is within 7 cm (was 3 cm); given up only beyond 7 cm. Arming still needs 5 cm, 4.5 to 25 N, under 0.05 m/s, 0.6 s. armtest always stiffens over 1.5 s first.
- **At arming:** for 0.25 s the target stays on the hand along the reach, and for 0.5 s the one-tick let-go test is off.
- **Let-go of a loaded idle hold:** pull over 10 N with under half of it read back (friction and a moving handle's reading allowed for): target onto the hand at once, then the 2 cm/s walk back.
- **Calibration (push, pull; `calibrate=False` skips it):** after setup, `Sample.phase == "calibrate"`, dial reported 0, `rep_idx` -1. The handle is held where it is at the arm's `k_max` (1500 N/m with `set_test_limits`, else 600). `snapshot()["calibration"]`: `waiting` until 2 N along the push direction, `pushing` for 3 s with `progress`, then `done` with `comfort_force_n` (mean over the steadiest 1 s), `resistance_n` (fraction x comfort, 3 to 15 N) and `fraction`. `skipped` with `resistance_n` 3 N and a `reason` for a push under 5 N, a let-go, 20 s without a push, or an arm stop. `null` for reach and armtest. `set_dial()` still overrides. After the push the target goes onto the hand and the usual idle hold takes over; `arming.reason` is "calibrating" during the phase.
- **`calibration_state_after`:** after a push or pull set with at least one rep, the fraction moves 0.05 up (all reps completed, none rescued, none slower than 6 s) or down, within 0.3 to 0.8.
- **Reps:** every start of a rep, try or circle gives exactly one `RepResult`, also when it ends on its first tick (zero metrics, not completed), at `stop()` or at `resume()`.
- **Measured:** 10 of 10 reps at grips of 6, 10 and 18 N with a 1 cm wobble (reach and push). Resistances for sim strengths 0.3 / 0.6 / 1.0: push 6.0 / 9.8 / 14.8 N, pull 4.6 / 8.4 / 13.4 N. A 40 N shove in idle trips the arm itself; after home and `resume()` the session finishes.
