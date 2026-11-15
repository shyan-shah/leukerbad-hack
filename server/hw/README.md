# server/hw: bring-up and motion-test scripts for the Flexiv Rizon 4

Scripts Shyan used on 14 Nov to connect to the arm and run the first motion test. They live in `server/`
because that is Shyan's folder; they drive the arm through Kian's `robot/arm.py` without changing it.
Results and what they mean: `context/BRINGUP_FINDINGS.md` and `context/MOTION_TEST.md`.

## Setup (arm laptop, once)

```
py -3.12 -m venv C:\venvs\flexiv17
C:\venvs\flexiv17\Scripts\python -m pip install flexivrdk==1.7.0 numpy
C:\venvs\flexiv17\Scripts\python -m pip install -r software\requirements.txt -r server\requirements.txt
```

- Robot software v3.9.3 needs `flexivrdk` **1.7.0** (not 1.9.x, never an unpinned install). The 1.7.0 wheel does not pull in numpy by itself.
- Laptop Ethernet: static `192.168.2.110`, mask `255.255.255.0`, no gateway. Controller is `192.168.2.100`.
- In Flexiv Elements: Settings → Remote Mode = **Ethernet**, then power-cycle the robot. Without that every connection fails with "Failed to connect".
- Run everything from the repo root.

**Serial.** Every script takes the serial from `robot/config.json`. While that file still has the placeholder, pass it explicitly: `--serial Rizon4-062157`.

## The arm is live as soon as it is powered

In Auto (Remote) mode the robot comes up already enabled (`operational()` is true). None of these scripts call `Enable()` or `ClearFault()`; the ones that command the arm refuse to start unless it is fault-free, operational, in IDLE mode and the e-stop is released. Before any script marked "moves the arm":

- one person with a hand on the e-stop, nobody within reach of the arm;
- read `robot/RUNBOOK.md`;
- remember that a running script cannot be stopped from another terminal. Ctrl+C in its own terminal stops it; the e-stop is the only instant stop.

## Scripts

| Script | Moves the arm? | What it does |
|---|---|---|
| `api_check.py` | no, no connection | Checks the installed `flexivrdk` has every call and field `robot/arm.py` uses. |
| `read_state.py` | no, read-only | Connects (retries 5 times, 20 s apart) and prints fault, operational, mode, all `info()` fields (licence, `K_x_nom`, software version), pose, joints, tool, and three wrench samples 5 s apart. Prints a `config.json` snippet for the start pose. |
| `tool_switch.py` | no motion commanded, **changes a robot setting** | Switches the selected tool (default `Flange`, meaning no tool) and reverts if the empty-arm force reading gets worse. |
| `motion_stages.py` | **yes** | Stages 1 to 4 of the first-motion test: hold, 2 cm move, soft hold, free axis. |
| `demo_motion.py` | **yes, larger and faster** | Continuous translation-only motion for videos, 4 minutes by default. |
| `run_studio.sh` | no | Starts Flexiv Elements Studio (Linux build) in WSL. PC-side app only. |
| `checked_arm.py` | not a script | `CheckedArm`, the arm class `python -m server.run --robot` uses. Same as `robot.arm.Arm`, but `connect()` never clears faults or enables: it refuses unless the robot is fault-free, operational, in IDLE, e-stop released and the expected tool (`--tool`, default `Flange`) is selected. |

### Read-only

```
C:\venvs\flexiv17\Scripts\python -m server.hw.api_check
C:\venvs\flexiv17\Scripts\python -m server.hw.read_state --serial Rizon4-062157
```

`read_state.py` only calls getters. Output also goes to `server/hw/out/read_state.json` (the `out/` folder is not committed).

### Tool switch

```
C:\venvs\flexiv17\Scripts\python -m server.hw.tool_switch Flange --serial Rizon4-062157
```

The robot's payload model changes, so the arm may twitch: keep clear. The motion scripts require the tool to be `Flange` while nothing is mounted. With the wrong tool mass the arm reads a false force (12.7 N on 14 Nov) and would drift centimetres at low stiffness. `tcp_pose` depends on the selected tool; `q` does not.

### Staged motion test

```
C:\venvs\flexiv17\Scripts\python -m server.hw.motion_stages 1 --serial Rizon4-062157
```

| Stage | Motion | Pass |
|---|---|---|
| 1 | hold 5 s at nominal stiffness | drift under 2 mm |
| 2 | 2 cm towards the base at 0.03 m/s and back, 600 N/m | ends within 3 mm |
| 3 | soft hold 20 s at 300 N/m; push the flange about 2 cm by hand and let go | returns within 5 mm |
| 4 | 20 s with 0 N/m on the reach axis (`reach_axis` in `robot/config.json`; override with `--axis x` or `--axis y`), 500 N/m on the others; slide it by hand about 3 cm | no trip |

Limits enforced in the script, on top of `Arm`'s own clamps and watchdog:

- speed limit 0.05 m/s, acceleration 0.3 m/s², stiffness at most 600 N/m (stage 1 only: nominal), contact limit `[30, 30, 30, 5, 5, 5]`;
- commanded targets at most 3 cm from the start;
- trips that call `robot.Stop()`: measured speed above 0.25 m/s, force change from the baseline above 25 N, hand outside a ±5 cm box;
- a hard time limit, and nominal stiffness restored on exit.

In stages 3 and 4, do not push further than about 4 cm or the box trip stops the run.

Stage 3 prints, per world axis, the displacement and force at the furthest point, the measured N/m (to compare with the commanded 300) and how far from the start it settled. Stage 4 prints the travel on the free axis, the drag force while it was moving and how far the two held axes moved.

### Video run

```
C:\venvs\flexiv17\Scripts\python -m server.hw.demo_motion --seconds 240 --serial Rizon4-062157
```

A smooth 3D loop, orientation locked: 3 to 11 cm in towards the base, 10 cm to each side, 2 to 12 cm up from wherever the flange is when it starts. It never goes further out or lower than the start, and returns to the start at the end.

**This goes beyond the staged-test limits**: up to about 19 cm from the start, about 0.10 m/s, 2000 N/m. Clear a box 13 cm deep, 25 cm wide and 15 cm tall in front of and above the flange, and watch the elbow.

- Trips that call `robot.Stop()`: measured speed above 0.30 m/s, force change above 25 N, leaving the envelope.
- Soft stop: create the file `server/hw/out/STOP`; it ramps down and stops within about 8 seconds.
- `--scale` speeds the pattern up or down (capped at 1.5). Leave it at 1.0 unless someone has checked the space again.

### Dry runs without the robot

`motion_stages.py` and `demo_motion.py` accept `--sim`, which runs them against Shiv's `software/sim_arm.py`. `--force-trip` (with `--sim`, stage 2) provokes a trip to check the stop path. The simulated arm sags about 1.3 cm under its simulated limb weight, so stage 2 "fails" in the sim; that is the sim, not the script.

### Elements Studio

```
wsl -d Ubuntu-22.04 -u shyan -- bash -lc "~/flexiv/studio-3.9.3/run_studio.sh"
```

`run_studio.sh` is the launcher installed at that path on Shyan's laptop (WSL Ubuntu 22.04 with `networkingMode=mirrored` in `.wslconfig`). In the window: REFRESH, then Connect. Use it only to check or set Remote Mode and to look at the licence. Decline every "update robot" prompt.

## Results from 14 Nov (`results/`)

| File | Content |
|---|---|
| `read_state_2026-11-14.json`, `read_tool_2026-11-14.json` | first successful read: state, `info()`, pose, joints, wrench, tool list (tool was still `Seat_Assembly_tool`) |
| `stage0.json`, `stage0a.json` | force baseline before, and state after, the switch to `Flange` |
| `stage1.json`, `stage1.csv` | hold: 0.153 mm drift, pass |
| `stage2.json`, `stage2.csv` | 2 cm move: reached 15.7 mm, ended 7.44 mm from the start, fail on the 3 mm mark |
| `demo.json` | 4-minute video run: no trips, peak 0.106 m/s, mean tracking lag 14.9 mm |

Stages 3 and 4 and the engine dry run have not been run yet.
