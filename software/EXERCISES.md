# Robot exercise programmes (E1)

Presets live in `software/exercises.py` (`EXERCISES`, `LIVE`); the engine applies one with
`Engine(..., exercise="<id>", reps=None)`. The app ids are those of `context/EXERCISE_MAP.md`.
All numbers are team-chosen starting values, not clinical prescriptions. Everything below was
tested on `SimArm` only (`software/tests/test_exercises.py`); nothing here has run on the real arm yet.

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
- **`setup`** (`Sample.phase == "setup"`, dial reported as 0): transparent along the line, walls on the other two axes, target on the hand. The patient moves the handle out to the far end. The arm never drives it there: with an empty handle nothing moves (tested for 8 s).
- When the hand has been within 2 cm of the far end for 1 s: `idle` (soft hold at the far end), then reps as usual. "out" is towards the patient; the band pulls back towards the far end in both phases.
- Setup is entered only at `start()`, and only if the hand is not already at the far end.
- Sim, strong patient: setup took 3.5 s, then 3 of 3 reps completed, peak 12.6 N.

### armtest (isometric)
- `idle`: soft hold until a hand has been on the handle at the start for 1 s. Then 3 tries: `out` = push for 3 s, `back` = rest for 5 s. After the last try: `idle`, `done`.
- During a push the target is the start pose, the reach axis is at `arm.limits.k_max` (600 N/m, the arm's own clamp) and the other axes at `K_WALL`. That stiffness stays on from the first try to the last.
- One `RepResult` per try: `mode "isometric"`, `peak_force_n` and `mean_force_n` are the force **along the reach axis in the push direction**, relative to the engine's force baseline; `rom_m` is the largest displacement; `contribution` 1.0; `completed` if the peak is over 5 N; `duration_s` the push time; `sparc` 0.
- A push that moves the handle more than 5 cm ends the try early (it is still recorded). With 600 N/m that is 30 N, the same as the arm's contact limit, so **readings top out at about 30 N**.
- **Rest is not a fixed target.** When a push ends the target is put on the hand and walked back to the start at 2 cm/s. With the target left on the start pose, the simulated patient relaxing from 20 N let the spring snap the handle back at 0.46 m/s, which tripped the speed limit and ended the session.
- Sim: strength 0.8 gives 20.1 N peak (patient's cap 20 N), 13.0 N mean, 3.5 cm displacement; strength 1.0 gives 25.1 N and 4.3 cm.

### circle (stretch, not live)
Robot-led: after the usual 1 s with a hand on the handle at the start, the target moves round the circle (start pose = nearest point, centre one radius along the reach) at 6 s per circle with 300 N/m on all three axes. No assist-as-needed and no tunnel. The target waits while the hand is more than 5 cm from it. One `RepResult` per circle (`mode "guided"`, `rom_m` = extent along the reach, path error = distance from the circle). Phase is `out` for the first half and `back` for the second.
- Sim, passive (limp) patient: 8 of 8 circles, 6.0 s each. The limb's 8 N sags the handle a constant 2.7 cm at 300 N/m; with that constant sag removed (the same rule as the line's path error) the hand stays within 1.5 cm of the circle. Without removing it the hand rides 2.7 cm below the circle, so "within 2 cm" holds only in that sense.

## Hands off

| kind | what happens when the person lets go | tested |
|---|---|---|
| assist (`reach`) | hands-off rule: the rep ends, the target is latched, the hand stops within 8 cm | yes |
| resist (`push`, `pull`) | never carried further along the reach. In the sim the band snaps the empty handle back at 0.40 m/s and the arm's speed trip puts it in hold (fault text set, session needs a restart) | yes |
| test (`armtest`) | never driven anywhere (stays within 5 cm). Letting go while pushing hard releases the spring: in the sim 0.46 m/s, speed trip, hold | yes |
| guided (`circle`) | the circle ends as not completed, phase `idle`, the target stops | yes |
| `pull` setup | nothing moves | yes |

The two speed trips are the arm's safety net working, but they end the session. Not changed here because they are section 4.2 behaviour: a gentler option for Shiv is to apply the hands-off rule on the resist side too (end the rep and latch the target where the handle was released).

## Simulated patient hooks (`software/sim_arm.py`)

`SimArm.reach_origin` (where the patient's reach starts), `SimArm.auto_cue` and `SimArm.cue("out" | "rest" | "back")`. The engine sets them in `start()`; for `pull` and `armtest` it cues the patient itself, for `reach`, `push` and `circle` the patient follows the stiffness change as before. Defaults reproduce the old behaviour.
