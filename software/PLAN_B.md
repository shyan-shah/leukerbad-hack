# PLAN B: what to run if the RDK licence blocks our control mode

Shiv, 2026-11-14 about 21:00. This is research only. Nothing in `robot/` was edited and nothing was run on the robot.
Robot: Rizon 4, software v3.9.3. RDK: `flexivrdk` 1.7.0, installed in `C:\venvs\leukerbad` and inspected there with `dir()` and `help()`.

## 1. Short answer

- **Our engine probably needs only the cheaper "Standard" licence, not "Professional".** Flexiv's v1.x manual says Professional adds "robot dynamics and real-time functionalities such as joint torque/position streaming, Cartesian motion/force streaming". Standard covers "essential and non-real-time functionalities such as reading robot states, sending plan/primitive commands". `NRT_CARTESIAN_MOTION_FORCE` is a non-real-time mode, so it most likely falls under Standard. **This is not verified.** The manual sorts features into licence tiers and never lists modes by name.
- **The risk we can actually see today is having no licence at all, not the wrong tier.** Shyan's packet capture (`docs/BRINGUP_FINDINGS.md`) shows the robot offers no `flexiv_rdk` topics. Without a licence the RDK server never starts, so no mode works: no primitives, no joint impedance, no free drive through the RDK.
- **Recommendation:**
  1. Keep plan A, the Cartesian spring in `NRT_CARTESIAN_MOTION_FORCE`.
  2. On first connect, run the 2-minute licence probe in section 4 before anything else.
  3. If the Cartesian mode is refused but primitives work, switch to **Plan B: free-drive assessment**. The arm floats (`FloatingCartesian` primitive), the engine runs with the dial locked at 0 (transparent), and we still show live reps, ROM, path error, smoothness and the report. This costs one new file in `software/` and one flag in `server/run.py` (Shyan).
  4. If there is no RDK at all, demo on `server.run --sim` and label it SIMULATED, as the master plan already does.
- **Do not plan on joint impedance as plan B.** Section 3 explains why: it likely needs the same licence, it needs our own inverse kinematics, and it loses the per-axis "tunnel walls".

## 2. What exists in flexivrdk 1.7.0 (from the installed library)

`flexivrdk.Mode` has exactly these members (`dir()` and `Mode.__doc__`):
`UNKNOWN, IDLE, NRT_JOINT_IMPEDANCE, NRT_JOINT_POSITION, NRT_PLAN_EXECUTION, NRT_PRIMITIVE_EXECUTION, NRT_CARTESIAN_MOTION_FORCE, NRT_SUPER_PRIMITIVE`.

**The Python package has no RT (real-time, 1 kHz) modes at all.** The manual's `RT_JOINT_TORQUE`, `RT_JOINT_IMPEDANCE`, `RT_JOINT_POSITION` and `RT_CARTESIAN_MOTION_FORCE` exist only in the C++ library. Every RT example in v1.7 is C++, for example `intermediate4_realtime_joint_floating.cpp` [E2]. So the Professional tier gives us nothing from Python. The one exception is `flexivrdk.Model` (Jacobian `J()`, mass matrix `M()`, gravity `g()`), which is "robot dynamics" and so probably Professional.

| Mode / feature | Python call in 1.7.0 | What it does | Licence (from the manual's wording) |
|---|---|---|---|
| `NRT_CARTESIAN_MOTION_FORCE` (plan A) | `SendCartesianMotionForce(pose, wrench=[0]*6, max_linear_vel=0.5, max_angular_vel=1.0, max_linear_acc=2.0, max_angular_acc=5.0)`, `SetCartesianImpedance(K_x[6], Z_x=[0.7]*6)`, `SetForceControlAxis`, `SetForceControlFrame`, `SetMaxContactWrench`, `SetNullSpacePosture` | The robot's own Cartesian impedance (spring) toward a target pose, with optional force control per axis | NRT, so probably Standard. **Unverified.** |
| `NRT_JOINT_IMPEDANCE` | `SendJointPosition(q, dq, ddq, max_vel, max_acc)` (5 lists, unnamed in 1.7.0), `SetJointImpedance(K_q, Z_q=[])` | Spring toward a joint-angle target, stiffness set per joint | NRT, so probably Standard. Unverified. |
| `NRT_JOINT_POSITION` | `SendJointPosition(...)` | Stiff joint position tracking | NRT, so probably Standard. Not useful to us: the arm is rigid. |
| `NRT_PRIMITIVE_EXECUTION` | `ExecutePrimitive(name, dict, block_until_started=True)`, `primitive_states()`, `busy()` | Built-in skills: `Home`, `MoveJ`, `MoveL`, `ZeroFTSensor`, and free drive (`FloatingCartesian`, `FloatingJoint`) | "sending plan/primitive commands" is explicitly Standard [M1]. Free drive "require[s] a license" [M3], tier not named. |
| `NRT_PLAN_EXECUTION` | `ExecutePlan(name or index)`, `plan_list()` | Runs plans saved in Elements, e.g. `PLAN-Home` | Standard [M1] |
| `NRT_SUPER_PRIMITIVE` | `SendCartesianMotionForce` | Motion inside a running primitive | Unclear |
| `flexivrdk.Model` | `Model(robot).J(link)`, `.M()`, `.g()`, `.reachable(...)` | Kinematics and dynamics | "robot dynamics", so probably Professional |
| Reading state | `states()` (`tcp_pose`, `tcp_vel`, `ext_wrench_in_world`, `q`, ...), `info()` (`license_type`, `K_x_nom`, `K_q_nom`, `software_ver`) | Read-only | Standard [M1] |

Version pairing: Flexiv's table lists "v1.7 | v3.9" [M4], which matches our robot (v3.9.3) and our pin.

## 3. The fallbacks, ordered by which licence state they survive

### State 1: no RDK licence (what the packet capture suggests today)
Nothing in the RDK works, because the server is not running. The options are:
- **Get a licence installed** (technician, Elements → licence page) and power-cycle. This is the only real fix.
- **Free drive from the teach pendant** in Elements (Manual: slide switch down, "Freedrive On", hold the enabling button) [M3]. This lets an actor move the arm by hand, but we cannot read any data, so it is useful only as a physical prop.
- **Read-only data stream ("DDK").** The robot does publish `rt/flexiv_ddk/basic_stream_data/...`. I found no public Flexiv DDK client: it is not among the ten repos visible on `github.com/flexivrobotics` (17 more were not listed), and PyPI could not be checked. If the organisers have one, it could feed live assessment while the arm is in pendant free drive. **Unverified, do not count on it.**
- **Demo on `server.run --sim`**, labelled SIMULATED. This is already green (I2).

### State 2: licence present, `NRT_CARTESIAN_MOTION_FORCE` refused, primitives allowed
**Plan B: free-drive assessment (recommended fallback).**
- `SwitchMode(NRT_PRIMITIVE_EXECUTION)`, then `ExecutePrimitive("FloatingCartesian", {})` [M3]. The arm becomes weightless and follows the hand. We keep reading `states()` at 100 Hz.
- The engine runs **with the dial locked at 0, manual mode** (`Engine(..., dial=0.0, auto=False)`). At `D = 0` the controller already sets the reach-axis stiffness to 0 (`software/controller.py`, `k_axis = 0.0`). So the commanded spring force along the reach axis is 0, and `metrics.contribution` scores the person's own work correctly, not "phantom" robot work. Reps, ROM, path error, SPARC, force and the report all work unchanged.
- **What we lose:** assistance, resistance, the tunnel walls, auto assist-as-needed and stall rescue. The pitch becomes "measurement today; assist and resist need the controller mode". That is honest and still shows the data story.
- **Safety changes:** the in-code clamps in `robot/arm.py` (target lead, stiffness cap, watchdog, `hold()`) no longer act, because we send no targets. The speed, force and box trips can still be *detected* in software, but the response becomes `Stop()` (free drive ends and the arm holds), not a soft hold. Flexiv warns that free drive "will be activated immediately regardless of whether the enabling button on the motion bar is pressed down" [M3]. We should check `enabling_button_pressed()` first. Technician-set Elements limits (TCP speed, safety plane) still apply. **The K2 sign-off must be redone for this mode.**
- **Unverified:**
  - the `FloatingCartesian` parameter names and how it ends on v3.9 (the v3.9 primitives page did not load; the manual's example passes `{}` and waits on `busy()`);
  - whether `ext_wrench_in_world` still reads hand force during free drive, which the engine needs to tell whether someone is holding the handle (the hands-off rule only applies at `D > 0`, so this only matters for arming a rep; the master plan's `POST /api/go` fallback covers it);
  - whether free drive stops by itself if the laptop disconnects.

**Plan B-prime (only if the mode works but `SetCartesianImpedance` is refused or ignored):** stay in `NRT_CARTESIAN_MOTION_FORCE`, call `SetForceControlAxis` to put the reach axis under force control, and send the spring force `K*(target - hand)` that Python computes as the `wrench` argument (pattern from `intermediate4_non_realtime_cartesian_motion_force_control.py` [E1]). Walls stay as stiff motion control on the other axes. **Cost:**
- It puts a force loop in Python at 100 Hz, which the master plan deliberately avoids.
- It breaks the "spring force bounded by construction" argument of section 4.2, so the 30 N bound must be enforced by clamping the wrench instead.

This needs an edit to `robot/arm.py` `_send_pose` / `_set_impedance` (Kian).

### State 3: licence present, every NRT motion mode allowed (the likely case)
Plan A as written. Nothing changes.

### Why not joint impedance
`NRT_JOINT_IMPEDANCE` looks like a natural second choice but is a poor plan B here:
- **Licence:** nothing in the manual suggests it is allowed when the Cartesian NRT mode is not. Both are non-real-time motion streaming.
- **Kinematics:** to turn our Cartesian target into joint targets we need a Jacobian or IK. `flexivrdk.Model.J()` is "robot dynamics" and is probably the Professional tier we would not have. Writing our own Rizon 4 forward kinematics from Flexiv's URDF (`flexiv_description`) is half a day of risky work.
- **Behaviour:** `SetJointImpedance` takes one stiffness per joint (a diagonal). The Cartesian stiffness that results depends on the pose and couples the axes, so we cannot have "stiff walls, free reach axis". Assist and resist would push the hand off the line.
- **Example to start from if ever needed:** `intermediate2_non_realtime_joint_impedance_control.py` [E1]: `SendJointPosition(target_pos, [0]*7, [0]*7, [2.0]*7, [3.0]*7)` and `SetJointImpedance(K_q_nom * 0.5)`.

## 4. First-connect licence probe (for Kian; paste into a REPL, nobody touching the arm)

Read-only except mode switches, which do not move the arm. Run it from `C:\venvs\flexiv17` or any venv with `flexivrdk==1.7.*`.

```python
import flexivrdk as f
r = f.Robot("Rizon4-062157")
i = r.info()
print("licence:", i.license_type, "| sw:", i.software_ver, "| K_x_nom:", list(i.K_x_nom))
if r.fault(): r.ClearFault()
r.Enable()
import time
while not r.operational(): time.sleep(0.1)
for m in ("NRT_CARTESIAN_MOTION_FORCE", "NRT_JOINT_IMPEDANCE", "NRT_PRIMITIVE_EXECUTION", "NRT_PLAN_EXECUTION"):
    try:
        r.SwitchMode(getattr(f.Mode, m)); time.sleep(0.3)
        print(m, "->", r.mode(), "| fault:", r.fault())
    except Exception as e:
        print(m, "REFUSED:", e)
# Also check that stiffness changes are accepted (the plan A dial depends on it):
r.SwitchMode(f.Mode.NRT_CARTESIAN_MOTION_FORCE)
try:
    r.SetCartesianImpedance([x * 0.5 for x in i.K_x_nom]); print("SetCartesianImpedance OK")
    r.SetCartesianImpedance(list(i.K_x_nom))
except Exception as e:
    print("SetCartesianImpedance REFUSED:", e)
r.Stop()
```

How to read it:
- Cartesian mode switches and stiffness is accepted: plan A.
- Cartesian mode is refused but primitive mode works: plan B.
- Cartesian mode switches but stiffness is refused: plan B-prime.
- `Robot(...)` itself fails: state 1 (licence or Remote Mode, see BRINGUP_FINDINGS).

Also record the `license_type` string in `BRINGUP_FINDINGS.md`.

## 5. Minimum code change for plan B

The engine and the frozen section 4.3 interface stay as they are. All of this is new code in `software/`; nothing is edited in `robot/`.

1. **New file `software/freedrive_arm.py`, class `FreeDriveArm`** (about 120 lines), with the same names as `Arm`:
   - `connect()`: same as `Arm.connect` (fault clear, enable, wait operational). Reuse the pure helpers from `robot.arm` (`load_config`, `check_trip`, `Limits`) by import, not by copy.
   - `zero_force()`: same `ZeroFTSensor` primitive.
   - `home()`: `ExecutePrimitive("MoveL", ...)` to the start pose, or skip it and use the current pose.
   - `start_compliance()`: refuse unless `enabling_button_pressed()` (configurable), then `SwitchMode(NRT_PRIMITIVE_EXECUTION)` and `ExecutePrimitive("FloatingCartesian", {})`. Record `start_pos` and set the mode to `"compliant"`.
   - `set_target()` and `set_stiffness()`: record the values only (so the engine's contribution bookkeeping is unchanged) and send nothing. Raise before `start_compliance()`, as section 4.3 requires.
   - `get_state()`: read `states()` exactly as `Arm._read` does. Run `check_trip`, and on a trip call `Stop()` and set the mode to `"hold"` with `fault` set.
   - `hold()` and `stop()`: `Stop()` (ends free drive; the robot holds position).
   - `close()`: `Stop()`.
   - No watchdog thread: there is no stream of targets to watch.
2. **Test `software/tests/test_freedrive_arm.py`** with a fake robot, following `robot/tests/test_arm_offline.py`. Check that no motion command is ever sent, that a trip calls `Stop()`, and that calls before `start_compliance()` raise.
3. **Server (Shyan, requested in LOG, not edited here):** `server/run.py` gets `--freedrive`. It builds `FreeDriveArm.from_config` and creates the engine with `dial=0.0, auto=False`. The dial UI is greyed out and labelled "measurement mode".
4. **Kian:** run the section 4 probe on first connect. Repeat the K2 release test and the technician sign-off for free drive before anyone holds the handle.

Effort: about 2 hours for 1 and 2, plus 15 minutes for 3. It can be written and tested offline now, and tried on the arm in 10 minutes once primitives are known to work.

## Sources

- [M1] Flexiv RDK manual v1.x, Activate RDK server (licence tiers): https://www.flexiv.com/software/rdk/manual/v1.x/activate_rdk_server.html
- [M2] Flexiv RDK manual v1.x, Control modes: https://www.flexiv.com/software/rdk/manual/v1.x/control_modes.html
- [M3] Flexiv RDK manual v1.x, Free drive: https://www.flexiv.com/software/rdk/manual/v1.x/free_drive.html
- [M4] Flexiv RDK manual v1.x, Robot software compatibility ("v1.7 | v3.9"): https://www.flexiv.com/software/rdk/manual/v1.x/robot_software_compatibility.html
- [E1] v1.7 Python examples: https://github.com/flexivrobotics/flexiv_rdk/tree/v1.7/example_py (`intermediate2_non_realtime_joint_impedance_control.py`, `intermediate3_non_realtime_cartesian_pure_motion_control.py`, `intermediate4_non_realtime_cartesian_motion_force_control.py`, `basics3_primitive_execution.py`)
- [E2] v1.7 C++ examples (all RT examples are C++): https://github.com/flexivrobotics/flexiv_rdk/tree/v1.7/example
- Primitives manual (it defaulted to 3E.1; the v3.9 page did not load): https://www.flexiv.com/software/primitives
- Could not reach: `rdk.flexiv.com` API docs (DNS failure), so `SetCartesianImpedance` limits (for example, whether 0 N/m is allowed) are unverified.
- Installed library: `flexivrdk` 1.7.0 in `C:\venvs\leukerbad`, read with `dir()` and `__doc__`.
