# Run book: Flexiv Rizon 4 rehab arm

Owner: Kian. Package K5. **Stub until K2 (safety sign-off) is done**; every line marked `TODO(confirm on arm)` must be checked on the real robot and the marker removed.

Read this out loud, step by step, every time the arm is switched on. Nobody skips steps because "it worked last time".

## Roles (fill in before every session)

| Role | Name | Job |
|------|------|-----|
| E-stop holder | TODO(confirm on arm) | Hand on the physical e-stop **whenever the arm is enabled**. Does nothing else. Presses on any doubt, no discussion. |
| Operator | TODO(confirm on arm) | At the laptop. Runs the commands below. Calls each step out loud. |
| Technician | TODO(confirm on arm) | Flexiv/organiser technician. Required for first power-on of the day, any fault that does not clear, and any change to Elements limits. |
| Person at the handle | healthy team member only | Never someone injured or impaired. Is an actor in the demo, described as one. |

E-stop location: TODO(confirm on arm) (from `robot/BRINGUP.md` answer 8).

## Fixed facts

- Robot: Rizon 4, serial `Rizon4-XXXXXX` TODO(confirm on arm), robot software TODO(confirm on arm).
- RDK: `flexivrdk==1.9.x` pinned in `robot/requirements.txt` (never a plain `pip install flexivrdk`). Python 3.12.
- Laptop network: static IP `192.168.2.x`, netmask `255.255.255.0`, no gateway. Python allowed through the Windows firewall.
- Elements limits set by the technician (speed, force, safety plane): see `robot/SAFETY.md`. TODO(confirm on arm)
- In-code limits: `robot/arm.py` `Limits` (MASTER_PLAN 4.2). The caller cannot override them.

## 1. Power-on to ready

1. **Area check.** Workspace clear, chair at the marked position (`robot/SETUP.md`), nobody within reach of the arm.
2. **Roles.** E-stop holder named and at the e-stop. Operator named. Say both names out loud.
3. **Power on** the control box. TODO(confirm on arm): switch location and boot time.
4. **Elements.** On the teach pendant / Elements: robot is in **Remote mode, Ethernet**; no fault shown; note the robot software version. If Remote mode had to be changed, power cycle. TODO(confirm on arm)
5. **E-stop release.** E-stop holder releases the e-stop, then keeps a hand on it from here on.
6. **Laptop.** Ethernet cable plugged in; IP is `192.168.2.x`. Open a terminal at the repo root, activate the venv:
   `C:\venvs\leukerbad\Scripts\activate` (outside the repo and OneDrive; setup and firewall steps in `robot/SETUP.md`).
7. **Status check** (changes nothing):
   `python robot/recover.py --check`
   Expect `connected True`, `fault False`. If it cannot connect, see **Faults: cannot connect**.
8. **Recover / enable.** Nobody touching the arm:
   `python robot/recover.py`
   Type `yes`. Expect `READY`. This clears any fault, enables, and restores nominal stiffness.
9. **Handle and tool.** Handle mounted and tight. Tool (handle mass and CoM) set in IDLE mode, as in `robot/BRINGUP.md`. TODO(confirm on arm): whether the tool must be re-selected after each power cycle.
10. **Home and zero.** Nobody touching. Operator runs `home()` then `zero_force()` (through `robot.arm`, or the server start-up if it does it). TODO(confirm on arm): exact command once K1/Y2 land. Then check force reads about 0 N with nobody touching (`python robot/recover.py --check`, `ext_wrench_in_world` within about ±1 N TODO(confirm on arm)).
11. **First touch of the day.** Technician pushes the handle first at soft hold (`k_hold`, 300 N/m) and confirms it feels soft and stable.
12. **Start the app:**
    `python -m server.run --robot Rizon4-XXXXXX`
    and in a second terminal `python -m server.watch`. Watch shows `arm_mode` and no SIMULATED tag.
13. **Start a session** (from the demo page or curl, see `server/API.md`). The person takes the handle only when the operator says "go".

Ready = steps 1 to 12 done, e-stop holder in place.

## 2. During a session

- Operator watches `server.watch`: dial, force, `arm_mode`. Any `hold` with a `fault` text: say it out loud, the person lets go.
- Soft stop at any time: `curl -X POST localhost:8000/api/hold`, or Ctrl+C in the `server.run` terminal (leaves the arm in hold).
- Hard stop: **e-stop**. Anyone may call "stop"; the e-stop holder presses.
- Swapping people at the handle: soft stop first, then swap, then start a new session.

## 3. Faults

General rule: **person lets go first, then diagnose.** If in doubt, e-stop.

| What you see | Likely cause | What to do |
|---|---|---|
| `arm_mode: hold`, `fault: "speed ..."` | Software trip: hand moved faster than `trip_speed` (0.40 m/s) | Person lets go. Normal, not a robot fault. Start a new session (calls `start_compliance()` again). If it repeats, slow down or report for K3 tuning. |
| `arm_mode: hold`, `fault: "force ..."` | Software trip: force above `trip_force` (40 N) | Person lets go. Check nobody is leaning on the handle. New session. Repeats: stop and tell Kian. |
| `arm_mode: hold`, `fault: "outside box ..."` | Hand more than 2 cm outside the workspace box | Person lets go. Check chair position against `robot/SETUP.md`. `home()` with nobody holding, new session. |
| `arm_mode: hold`, `fault: "watchdog ..."` | No target for 0.2 s: engine stalled, laptop busy, or server crashed | Person lets go. Check the `server.run` terminal for a traceback. Restart the server, run `python robot/recover.py`, new session. |
| Arm stops, Elements shows a fault (e.g. contact wrench / collision) | Robot-side safety (`SetMaxContactWrench` 30 N or Elements limits) | Person lets go. `python robot/recover.py`. If it reports `FAULT DID NOT CLEAR`, call the technician. TODO(confirm on arm): which faults ClearFault can clear. |
| E-stop pressed | Someone pressed it | Find out why before releasing. Person away from the arm. Release e-stop, `python robot/recover.py`, then step 10 (home, zero) again. TODO(confirm on arm): whether e-stop release needs extra steps in Elements. |
| Laptop / Ethernet lost | Cable, laptop sleep, crash | Robot stops and holds by itself. Person lets go. Reconnect, `python robot/recover.py`, restart the server. Disable laptop sleep. |
| `recover.py` says `CANNOT CONNECT` | Network, firewall, Remote mode, licence, serial | Check cable and IP `192.168.2.x`, firewall rule for Python, Elements in Remote mode (power cycle after changing), serial string exact. Still failing: technician. |
| `recover.py` says `NOT OPERATIONAL` | E-stop still pressed, not in Remote mode, brakes | Release e-stop, check Elements, run again. |
| `SwitchMode` error / licence error | RDK licence or mode not enabled | Technician. Nothing we can fix in code. |
| Handle feels floppy or too stiff with no program running | Stiffness left on the robot by a crashed program | `python robot/recover.py` (restores `K_x_nom`). |
| Force reads non-zero with nobody touching | Sensor drift, tool settings wrong, handle loose | Tighten handle, check tool settings, `zero_force()` with nobody touching. |
| Vibration or buzzing at the handle | Stiffness too high or bad tuning | Soft stop. Report to Kian for K3. Do not continue with a person on it. |
| Anything unexpected | | E-stop. Person away. Technician. |

## 4. Shutdown

1. Person lets go and steps back.
2. Stop the session (demo page or `curl -X POST localhost:8000/api/session/stop`). Exports are written.
3. Ctrl+C `server.run`. It calls `hold()` then `close()`, which restores nominal stiffness and stops the robot.
4. If the server crashed instead of closing cleanly: `python robot/recover.py` (restores nominal stiffness, leaves the robot in IDLE).
5. Optional: `home()` with nobody touching, so the arm is parked for the next team. TODO(confirm on arm): agreed park pose with the technician.
6. E-stop holder presses the e-stop. Then (and only then) the e-stop holder may leave.
7. Power off the control box per the technician. TODO(confirm on arm): Elements shutdown sequence.
8. Append to `context/LOG.md` anything that faulted, and to `robot/SAFETY.md` any safety event.

## 5. To confirm on the arm (checklist for K2)

- [ ] Names for e-stop holder, operator, technician; e-stop location.
- [ ] Serial, robot software version, pinned RDK version.
- [ ] Power-on, Elements Remote mode and shutdown sequence.
- [ ] `recover.py`: which RDK getters exist; `ClearFault()` return type; time to operational; `SwitchMode` holds pose with no jump; nominal stiffness persists after `Stop()`.
- [ ] Which faults `ClearFault()` clears and which need a power cycle or the technician.
- [ ] E-stop release procedure.
- [ ] Tool setting survives a power cycle or not.
- [ ] Untouched force tolerance after zeroing.
- [ ] Exact home/zero commands once K1 and Y2 exist.
