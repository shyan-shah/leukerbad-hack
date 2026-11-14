# Arm bring-up findings (Shyan, 2026-11-14, updated about 21:25 Swiss time)

**The arm is connected.** Read-only work from Shyan's laptop: nothing was enabled, moved, changed or
updated on the robot by these scripts, and nothing in `robot/` was edited. For Kian.

## 1. Probe result: CONNECTED

`flexivrdk.Robot("Rizon4-062157")` connected on the first attempt from Windows
(`C:\venvs\flexiv17`, Python 3.12.10, `flexivrdk==1.7.0`, numpy), laptop clock 20:19:43.

What fixed it: Shyan set Settings → Remote Mode to **Ethernet** in Elements Studio and rebooted the robot.
Before that the robot only published its read-only `flexiv_ddk` topics and none of the `flexiv_rdk` ones
(seen in a packet capture), so every RDK version failed with "Failed to connect". Network, firewall and
serial were never the problem.

| Getter | Value |
|---|---|
| `connected()` | True |
| `fault()` | False |
| `operational()` | **True** |
| `operational_status()` | `READY` |
| `estop_released()` | True |
| `mode()` | `IDLE` |
| `busy()` / `stopped()` | False / True |
| `recovery()` / `reduced()` | False / False |

**Safety note: the robot was already enabled (`operational() == True`, status `READY`) when the probe
connected.** The probe never calls `Enable()`. So in Auto (Remote) mode after boot the arm is live as soon as
a program switches mode. Treat it as enabled whenever it is powered: e-stop holder in place before any script
that does more than read.

## 2. `info()`

| Field | Value |
|---|---|
| `serial_num` | `Rizon4-062157` |
| `model_name` | `Rizon4` |
| `software_ver` | `v3.9.3` |
| `license_type` | **`RDK-Professional+TDK-Standard`** (RDK log line: "Validated license: RDK-Professional") |
| `K_x_nom` | **`[10000, 10000, 10000, 1500, 1500, 1500]`** (N/m, N/m, N/m, Nm/rad x3) |
| `K_q_nom` | `[6000, 6000, 4200, 4200, 1500, 1500, 1500]` |
| `DoF` | 7 |
| `q_min` (rad) | `[-2.7926, -2.2690, -2.9671, -1.8675, -2.9671, -1.3963, -2.9671]` |
| `q_max` (rad) | `[2.7926, 2.2690, 2.9671, 2.6878, 2.9671, 4.5379, 2.9671]` |
| `dq_max` (rad/s) | `[2.094, 2.094, 2.443, 2.443, 4.887, 4.887, 4.887]` |
| `tau_max` (Nm) | `[123, 123, 64, 64, 39, 39, 39]` |

`k_max` in `arm.py` `Limits` is well under the nominal 10000 N/m, so stiffness clamping is set by our own limit.

## 3. Start pose (arm placed by hand by Shyan, read at 20:19 laptop clock)

```
tcp_pose = [0.805597, 0.449626, 0.619889, 0.720262, -0.127445, -0.104004, -0.673917]   # x y z (m), qw qx qy qz, world frame
q        = [0.983714, -1.800170, -1.986748, 0.989766, -1.113379, 0.253691, 1.555811]   # rad
flange_pose = [0.780451, 0.401946, 0.437905, 0.727380, -0.008484, 0.022648, -0.685809]
tcp_vel  = about 0 (under 0.0006 on every axis)
```

A second read 2 minutes later matched to 0.01 mm, so the arm is holding still.

`robot/config.json` snippet (format already matches: x, y, z, qw, qx, qy, qz, then 7 joint angles):

```json
"serial": "Rizon4-062157",
"start_pose": {
  "tcp_pose": [0.805597, 0.449626, 0.619889, 0.720262, -0.127445, -0.104004, -0.673917],
  "q": [0.983714, -1.800170, -1.986748, 0.989766, -1.113379, 0.253691, 1.555811]
}
```

Then remove `"serial"` and `"start_pose"` from `placeholders`.

**Three cautions before trusting this pose:**

1. **`tcp_pose` depends on the selected tool.** The active tool is another team's `Seat_Assembly_tool`, whose
   TCP is offset from the flange by `[-0.050, 0.020, 0.182]` m plus a rotation. If the tool is changed to our
   handle (or to `Flange`), the same arm posture gives a different `tcp_pose`. `q` and `flange_pose` do not
   change. Re-read `tcp_pose` after the tool is set and before `home()` is ever used.
2. **The reach direction is not along a base axis.** The TCP is at x = 0.81, y = 0.45, so a forward reach
   from here is probably diagonal in the world frame. `config.json` `reach_axis` (0 = x, 1 = y) and
   `force_sign` are still placeholders and need a decision or a measurement.
3. **The arm may be near the edge of its reach.** The flange is about 0.88 m from the base axis horizontally.
   Check there is really 35 cm of travel away from the body from this pose before using it for the demo.

## 4. Wrench with nothing touching (`states().ext_wrench_in_world`, 5 s apart)

| Reading | Fx (N) | Fy (N) | Fz (N) | Mx (Nm) | My (Nm) | Mz (Nm) |
|---|---|---|---|---|---|---|
| 1 | -1.293 | -0.446 | 12.520 | -1.255 | -0.199 | -0.090 |
| 2 | -1.344 | -0.492 | 12.532 | -1.270 | -0.181 | -0.091 |
| 3 | -1.772 | -0.583 | 12.509 | -1.307 | -0.048 | -0.106 |

- **Offset is about 12.6 N, almost all +z.** The selected tool `Seat_Assembly_tool` is configured as
  1.338 kg (13.1 N of weight) with CoM `[0.027, 0.032, 0.016]` m. The offset is about that weight, so the
  likely cause is that this tool is selected in software but not mounted. Not verified by looking at the flange.
- **Drift over 10 s:** Fx moved 0.48 N, Fy 0.14 N, Fz 0.02 N.
- **Consequences:** Shiv's engine refuses to start when the empty handle reads over 3 N, and `trip_force`
  is 40 N, so the force must be fixed before any session: set our handle as the tool (mass and CoM), then
  `zero_force()` with nobody touching.
- **`states().ft_sensor_raw` reads all zeros**, and the model is `Rizon4` (not 4s). That suggests there is no
  wrist force/torque sensor and the wrench is estimated from joint torques. If so, expect more noise than a
  sensor would give, and `ZeroFTSensor` needs testing on this arm (see section 5).

Tools stored on the robot: `Flange`, `Seat_Assembly_tool`, `E_RubberKnife`, `E_RubberKnife_copy`,
`Flexiv-GN01`, `Robotiq-2F-85`, `Robotiq-Hand-E`, `GripperDahuan`, `Mirka-AIROS-550CV`, `OnRobot-Sander`.
Our handle is not among them.

## 5. `robot/arm.py` and `robot/recover.py` against flexivrdk 1.7.0

"Live" means read from the connected robot. "Signature" means read from the installed module only; these
are commands, so they were not called (read-only rule).

| Call or field | In 1.7.0 | Verdict |
|---|---|---|
| `flexivrdk.Robot(serial)` | `Robot(robot_sn, network_interface_whitelist=[], verbose=True)` | OK, live |
| `fault()`, `operational()`, `mode()`, `info()`, `states()` | same | OK, live |
| `info().K_x_nom` | 6 values | OK, live |
| `states().tcp_pose` (7), `.tcp_vel` (6), `.ext_wrench_in_world` (6), `.q` (7) | all present | OK, live |
| `primitive_states()` | returns a dict; live value `{'primitiveName': 'Hold', 'terminated': 0, 'timePeriod': ...}` | OK, live. The `"terminated"` key exists. |
| `flexivrdk.Tool(robot)`, `.name()`, `.list()`, `.params()`; `ToolParams.mass`, `.CoM`, `.inertia`, `.tcp_location` | present | OK, live (getters). `Tool.Add/Switch/Update/Remove` exist, signature only. Not used in `arm.py` today. |
| `ClearFault()` | `ClearFault(timeout_sec=30) -> bool` | OK, signature |
| `Enable()`, `Stop()` | no arguments | OK, signature |
| `SwitchMode(Mode.NRT_CARTESIAN_MOTION_FORCE)` / `Mode.NRT_PRIMITIVE_EXECUTION` | both enum members exist | OK, signature. Not yet proven that the licence allows the switch, but `RDK-Professional` should. |
| `SendCartesianMotionForce(...)` | `(pose[7], wrench[6]=0, max_linear_vel=0.5, max_angular_vel=1.0, max_linear_acc=2.0, max_angular_acc=5.0)` | **Was wrong (7 arguments with a 1.9-only `velocity`), now fixed on main** by Shiv with Kian's OK: `arm.py` passes 6 arguments. |
| `SetCartesianImpedance(K_x)` | `(K_x[6], Z_x[6]=[0.7]*6)` | OK, signature |
| `SetMaxContactWrench([6])` | one list of 6 | OK, signature |
| `ExecutePrimitive("ZeroFTSensor", dict())` | `(primitive_name, input_params, block_until_started=True)` | Signature OK. **Whether `ZeroFTSensor` exists and works on this arm is untested** and is the main open API question, given `ft_sensor_raw` is all zeros. |
| In 1.9 but not in 1.7.0 | `SetMaxContactTorque`, `SetJointInertiaScale`, `SendMultiCartesianMotionForce`, `SetTimelinessFailureLimit`, `actions`, `lite`; fields `RobotInfo.has_FT_sensor`, `RobotStates.timestamp`, `.temperature`, `.tau_interact` | not used by `arm.py` or `recover.py` |

## 6. What Kian does next, in order

Already done on main: `robot/requirements.txt` (`flexivrdk==1.7.*`, `numpy`) and the `_send_pose` fix.

1. **`robot/config.json`**: set `"serial": "Rizon4-062157"` and remove it from `placeholders`. The arm will
   not connect through `robot.arm` until this is done.
2. **Tool first, with the technician**: mount the handle, add it as a tool (mass under 100 g error, CoM),
   and switch to it instead of `Seat_Assembly_tool`. This changes `tcp_pose` and should remove the 12.6 N offset.
3. **Re-read the start pose** with the handle tool active
   (`C:\venvs\flexiv17\Scripts\python.exe %TEMP%\flexiv_diag\read_state2.py Rizon4-062157` on Shyan's laptop,
   or K0 script `01_read.py`), then paste `tcp_pose` and `q` into `config.json`. Until then use the snippet
   in section 3 only together with `Seat_Assembly_tool`.
4. **Test `ZeroFTSensor`** with nobody touching and the e-stop held, and confirm the wrench reads about 0 N
   afterwards. If the primitive is refused, tell Shiv (the engine has an empty-handle baseline as a fallback).
5. **Decide `reach_axis` and measure `force_sign`** (push toward the reach direction, read the sign).
6. **Run the licence check in `software/PLAN_B.md` section 4**: with `RDK-Professional`, plan A
   (`NRT_CARTESIAN_MOTION_FORCE`) should be allowed; the first `SwitchMode` proves it.
7. **Docs**: change the remaining "1.9.x" mentions in `robot/SETUP.md`, `robot/RUNBOOK.md`, `robot/recover.py`.
   Add to the RUNBOOK that the arm comes up already enabled in Auto (Remote) mode.

## 7. Tools on Shyan's laptop

- `C:\venvs\flexiv17`: Python 3.12.10, `flexivrdk==1.7.0`, numpy. This one connects to the arm.
- `C:\venvs\leukerbad`: project requirements, no `flexivrdk`. Offline tests: 256 passed (earlier today).
- `%TEMP%\flexiv_diag\read_state2.py`: read-only probe (state, info, pose, joints, three wrench samples, JSON).
  `%TEMP%\flexiv_diag\read_tool.py`: read-only tool and primitive-state getters.
- Elements Studio 3.9.3 (Linux build in WSL): `C:\Users\shyan\Desktop\Start Flexiv Studio.bat`, then REFRESH
  and Connect. Command: `wsl -d Ubuntu-22.04 -u shyan -- bash -lc "~/flexiv/studio-3.9.3/run_studio.sh"`.
- Laptop network: `Ethernet 3` static `192.168.2.110/24`, no gateway. Controller `192.168.2.100`.
  Internal serial shown by Elements: `A02L-07-M2-062157`.
