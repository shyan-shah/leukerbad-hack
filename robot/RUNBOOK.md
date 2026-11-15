# Run book: Flexiv Rizon 4 rehab arm

Owner: Kian. Package K5. Updated 15 Nov with what happened on the arm on 14-15 Nov.
Lines still marked `TODO(confirm on arm)` have not been seen on the robot yet.

Read this out loud, step by step, every time the arm is switched on. Nobody skips steps because "it worked last time".

**Two rules above all others**

1. **The arm is live as soon as it is powered.** In Auto (Remote) mode it can come up already
   enabled with no command from us (seen 14 Nov). E-stop holder in place before power-on, not
   before "go".
2. **One laptop drives the arm at a time.** Say out loud who has it. Nobody else opens an RDK
   connection, not even a read-only one, until they hear "arm is free".

## Roles for the pitch and every session

PROPOSED 15 Nov, to confirm at the first rehearsal (change the names here if they change).
One person holds one role at a time. The presenter is not in this table and never touches the arm.

| Role | Name | Backup | Job |
|------|------|--------|-----|
| Operator | Shyan | Kian | At the arm laptop. Runs the commands below and calls each step out loud. Says "go" and "stop". |
| E-stop holder | Kian | Shiv | Hand on the physical e-stop **whenever the arm is powered**. Does nothing else, does not watch the screen. Presses on any doubt, no discussion. |
| Patient actor | Shiv | Gio | Healthy team member, introduced as "a team member acting as a patient". Takes the handle only when the operator says "go". Lets go at once on "stop" or on any surprise. |
| Technician | organiser's Flexiv technician | none | Required for the handle mounting, the safety checks (`robot/SAFETY.md`), any fault that does not clear, and any change to Elements limits. |

If a backup steps in, their own role goes to their backup first. If that cannot be filled, no session.

Nobody injured or impaired ever holds the handle. Nobody holds it at all until `robot/SAFETY.md` is signed.

E-stop location: TODO(confirm on arm). Write it here before the first session and make sure both e-stop holders have pressed and released it once with the arm in a safe state.

## Fixed facts

- Robot: Rizon 4, serial `Rizon4-062157` (Elements shows `A02L-07-M2-062157`), robot software v3.9.3, licence RDK-Professional.
- RDK: `flexivrdk==1.7.0` (never a plain `pip install flexivrdk`; 1.9.x and 2.x do not match this robot). Python 3.12.
- Arm laptop: Shyan's. Venv `C:\venvs\flexiv17`. Ethernet static `192.168.2.110`, mask `255.255.255.0`, no gateway. Controller `192.168.2.100`.
- `K_x_nom = [10000, 10000, 10000, 1500, 1500, 1500]`.
- **No wrist force/torque sensor.** Force is estimated from the joint torques, so it is only right when the active tool's mass and centre of mass are right. Tool for sessions: `RehabHandle` (`robot/tool_handle.md`). With nothing mounted the tool must be `Flange`.
- Elements Studio 3.9.3 on the arm laptop: double-click **`Start Flexiv Studio.bat`** on the desktop, then REFRESH, then Connect. Decline every "update robot" prompt.
- **Motion Bar switch: up = Auto (Remote), down = Manual.** Our code only works in Auto (Remote).
- Elements limits set by the technician (speed, force, safety plane): `robot/SAFETY.md`.
- In-code limits: `robot/arm.py` `Limits`. The caller cannot override them and nobody loosens them.

## 1. Power-on to ready

Cold start: once `Start Demo.bat` exists on the arm laptop's desktop, steps 6 to 12 are "double-click `Start Demo.bat`" (it does not exist yet, 15 Nov; until then type the commands).

1. **Area check.** Workspace clear, chair at the marked position (`robot/SETUP.md`), nobody within reach of the arm.
2. **Roles.** E-stop holder at the e-stop, operator at the laptop. Say both names out loud. From here on treat the arm as live.
3. **Cables.** Arm cable seated at BOTH ends (arm base and control box), Ethernet from the control box to the laptop.
4. **Power on** the control box. Motion Bar switch **up (Auto / Remote)**. TODO(confirm on arm): boot time.
5. **Elements.** Open Studio (`Start Flexiv Studio.bat`, REFRESH, Connect). Check, in this order:
   - No "Robot and Control Box are disconnected" message (if there is, see Faults).
   - Bell icon: no fault listed.
   - Settings → Remote Mode = **Ethernet**. If you had to change it, **reboot the robot**; it does not take effect until then.
   - If the robot is not enabled: press **Servo ON**. It may already be enabled; that is normal.
6. **Laptop.** Terminal at the repo root. Use the arm venv: `C:\venvs\flexiv17\Scripts\activate`.
7. **Status check** (changes nothing): `python robot/recover.py --check`
   Expect `connected True`, `fault False`, `operational True`, mode IDLE. If it cannot connect, see Faults.
8. **Tool.** `python robot/read_tool_force.py` (read-only, nobody touching). Expect tool `RehabHandle` and an empty force under about 2 N. If the tool is wrong or the force is high, fix it in Elements (`robot/tool_handle.md`) before going on. TODO(confirm on arm): whether the selected tool survives a power cycle.
9. **Handle.** Mounted, four M6 screws hand-tight plus a quarter turn, grip does not rotate.
10. **Start the app:**
    `python -m server.run --robot Rizon4-062157 --tool RehabHandle`
    (add `--reach-sign` only if `robot/config.json` does not have the right direction). The server refuses to start unless the robot is fault-free, operational, in IDLE, e-stop released and the tool matches. It never enables the robot or clears a fault. Second terminal: `python -m server.watch`. Watch shows `arm_mode` and no SIMULATED tag.
11. **Prepare.** Nobody touching: operator screen "Prepare", or `curl -X POST localhost:8000/api/arm/prepare`. It checks the arm and reads the empty-handle force. Sessions are refused (409) until this has succeeded.
12. **First touch of the day.** The technician (or, after sign-off, the operator) pushes the handle at soft hold and confirms it feels soft and springs back.
13. **Start a session** (operator screen or `server/API.md`). The patient actor takes the handle only when the operator says "go".

Ready = steps 1 to 12 done, e-stop holder in place.

`python robot/recover.py` (without `--check`) is only for recovery: it clears a fault, enables if needed and restores nominal stiffness. Nobody touching, type `yes`.

## 2. During a session

- Operator watches `server.watch`: dial, force, `arm_mode`. Any `hold` with a `fault` text: say it out loud, the patient actor lets go.
- Soft stop at any time: `curl -X POST localhost:8000/api/hold`, or Ctrl+C in the `server.run` terminal (hold, then a clean close).
- Hard stop: **e-stop**. Anyone may call "stop"; the e-stop holder presses.
- Swapping people at the handle: soft stop first, then swap, then start a new session.
- Between sets, with nobody touching: run Prepare again (the empty-handle force drifts).
- `armtest` (push and hold): push gently. Above about 30 N the handle gives way by design and at 40 N the arm drops into hold (`robot/SAFETY.md` finding 2).
- `push` and `pull`: do not let go mid-rep on purpose. The band pulls the empty handle back and the speed trip may put the arm in hold (safe; the session then needs a restart).

## 3. Faults

General rule: **the person lets go first, then diagnose.** If in doubt, e-stop.

| What you see | Cause | What to do |
|---|---|---|
| Elements: **"Robot and Control Box are disconnected"** | Loose arm cable (14 Nov) | Power OFF the control box. Reseat the arm cable at both ends. Power on. Do not reseat a cable with the power on. |
| RDK "Failed to connect" every time, ping works | Remote Mode is not Ethernet, or it was changed without a reboot (14 Nov) | Elements → Settings → Remote Mode = Ethernet, **then reboot the robot**. |
| `operational False`, no fault | Not enabled, e-stop pressed, or Motion Bar switch down (Manual) | Release the e-stop, switch up (Auto / Remote), press **Servo ON** in Elements. |
| **Critical fault** (bell icon red, arm will not enable) | Robot-side fault | **Read the bell first** and write down what it says (LOG.md). Then **reboot the robot**. `recover.py` will not clear a critical fault. If it returns after the reboot: technician. |
| `arm_mode: hold`, `fault: "speed ..."` | Software trip: hand faster than 0.40 m/s (also after letting go against the band) | Person lets go. Not a robot fault. Start a new session. If it repeats, slow down and tell Kian. |
| `arm_mode: hold`, `fault: "force ..."` | Software trip: force above 40 N | Person lets go. Check nobody is leaning on the handle. New session. Repeats: stop and tell Kian. |
| `arm_mode: hold`, `fault: "hand ... outside workspace box"` | Hand more than 2 cm outside the box | Person lets go. Check the chair position against `robot/SETUP.md`. New session from the start pose. |
| `arm_mode: hold`, `fault: "watchdog ..."` | No target for 0.2 s: engine stalled, laptop busy, server crashed | Person lets go. Read the `server.run` terminal. Restart the server, then Prepare. |
| Arm stops, Elements shows a fault (contact / collision) | Robot-side limit (`SetMaxContactWrench` 30 N or Elements limits) | Person lets go. Read the bell. `python robot/recover.py`. `FAULT DID NOT CLEAR`: reboot, then technician. TODO(confirm on arm): which faults ClearFault clears. |
| Server refuses to start: "arm not ready: ..." | Fault, not operational, not IDLE, e-stop, or wrong tool | Do what the message says. "not IDLE" usually means another laptop or script is driving the arm. Wrong tool: `robot/tool_handle.md`. |
| Session refused: "prepare the arm first" or "run zero_force" | Not prepared, or the empty handle reads over 3 N | Nobody touching, run Prepare. Still over 3 N: `python robot/read_tool_force.py` and follow its hint (tool mass or CoM is off, or something is resting on the handle). |
| E-stop pressed | Someone pressed it | Find out why before releasing. Person away from the arm. Release, Servo ON in Elements if needed, `python robot/recover.py`, then from step 7. TODO(confirm on arm): exact release steps. |
| Laptop / Ethernet lost | Cable, laptop sleep, crash | The robot stops and holds by itself. Person lets go. Reconnect, `python robot/recover.py`, restart the server. Laptop sleep must be disabled. |
| Handle feels floppy or too stiff with no program running | Stiffness left on the robot by a crashed program | `python robot/recover.py` (restores `K_x_nom`). |
| Force reads non-zero with nobody touching | Wrong tool selected, tool mass/CoM off, handle loose | `python robot/read_tool_force.py`. Tighten the handle, fix the tool in Elements. On 14 Nov a wrong tool gave 12.6 N. |
| Free axis drifts by itself | Tool mass/CoM off | Stop. Fix the tool. Nobody on the handle until `read_tool_force.py` is under 2 N. |
| Vibration or buzzing at the handle | Stiffness or tuning | Soft stop. Tell Kian (`robot/TUNING.md`). Do not continue with a person on it. |
| Anything unexpected | | E-stop. Person away. Technician. |

## 4. Shutdown

1. The person lets go and steps back.
2. Stop the session (operator screen or `curl -X POST localhost:8000/api/session/stop`). Exports are written.
3. Ctrl+C `server.run`. It calls `hold()` then `close()`, which restores nominal stiffness and stops the robot (IDLE).
4. If the server crashed instead of closing cleanly: `python robot/recover.py`.
5. E-stop holder presses the e-stop. Only then may the e-stop holder leave.
6. Say "arm is free" to the team, or power off the control box per the technician. TODO(confirm on arm): Elements shutdown sequence and the park pose for the next team.
7. Append to `context/LOG.md` anything that faulted, and to `robot/SAFETY.md` any safety event.

## 5. Confirmed on the arm, and still open

Confirmed 14-15 Nov: serial, robot software and RDK version; Remote Mode = Ethernet needs a
reboot; the arm can be enabled at power-on; RDK getters used by `recover.py` exist in 1.7.0;
`SwitchMode` to Cartesian mode holds the pose (0.15 mm drift in 5 s); nominal stiffness is
restored by `close()` and the robot ends in IDLE without a fault; the loose-cable message.

Still open:

- [ ] E-stop location, and both e-stop holders have tried it.
- [ ] Boot time; Elements shutdown sequence; park pose.
- [ ] Which faults `ClearFault()` clears (it has not been called on this arm yet).
- [ ] E-stop release procedure.
- [ ] Whether the selected tool survives a power cycle.
- [ ] `Start Demo.bat` written and tried from a cold start.
- [ ] Role names confirmed at a rehearsal.
