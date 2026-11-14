# Arm bring-up findings (Shyan, 2026-11-14 about 19:30)

Read-only work from Shyan's laptop. Nothing was enabled, moved, changed or updated on the robot.
Nothing in `robot/` was edited. For Kian.

## 1. Probe result: NOT CONNECTED

`flexivrdk.Robot("Rizon4-062157")` fails every time with "Failed to connect" after a 2 s search.

| Where | RDK | Attempts | Result |
|---|---|---|---|
| Windows, `C:\venvs\flexiv17` (Python 3.12.10) | 1.7.0 | 5 at 19:19 and 5 at 20:03, 20 s apart | failed |
| WSL Ubuntu 22.04, mirrored networking (Python 3.10) | 1.7.0 | 8 around 19:21, 5 at 20:05 (Studio closed), 20 s apart | failed |
| Windows, temp venv (earlier today) | 1.9.4.1 | 27 | failed |

So none of these could be read: `fault()`, `operational()`, `mode()`, `info()` (licence type, `K_x_nom`,
software version), `tcp_pose`, `q`, wrench. **The start pose and the three wrench readings are not captured.**

## 2. Why it fails (packet capture, not a guess)

A passive capture on the robot interface during a probe shows:

- The laptop and the robot do talk DDS. The network, firewall and serial are fine.
- The serial is right: the robot's topics are named `Rizon4_062157`.
- The robot (nodes `ext_ethernet_default_node`, `ext_ethernet_rt_udp_node`) offers only these topics:
  `rt/flexiv_ddk/basic_stream_data/Rizon4_062157`, `rt/flexiv_ddk/robot_log/...`,
  `rt/flexiv_ddk/non_stream_rpc/..._request` and `_reply`.
- The RDK asks for `rt/flexiv_rdk/RPC/..._request` and `_reply`, `rt/flexiv_rdk/heartbeat/...`,
  `rt/flexiv_rdk/rt_states/...`, `rt/flexiv_rdk/motion_commands/...`. **The robot offers none of them.**

The 20:05 capture shows the same thing. Firewalls are ruled out: Windows has inbound allow rules for the
Python interpreters, the WSL (Hyper-V) firewall default is inbound Allow, and the capture shows traffic both ways.

Elements sees the robot and the RDK does not, which is the pattern for "Remote Mode for RDK not active or
RDK licence missing".

Reading: the robot's RDK server is not running. The robot is only publishing its read-only data stream
(Flexiv "DDK"). Most likely causes, in order:

1. **No RDK licence installed on this robot.** Flexiv's manual lists "install an RDK license through
   Flexiv Elements" as step 1 of activating the RDK server. Not verified: nobody has read the licence page yet.
2. Remote Mode is on but not set to "Ethernet" (Elements Studio log at 19:00 shows it being enabled, then
   switched to GPIO, then enabled again), or the robot was not power-cycled after the last change.
3. Less likely: RDK 1.7.0 and robot 3.9.3 name their topics differently. Flexiv's table pairs v3.9 with RDK v1.7.

**What to ask the technician / organisers:** "Does Rizon4-062157 have an RDK licence installed? In Elements,
Settings → Remote Mode must be Ethernet, saved, then power-cycle."

## 3. Facts confirmed today

| Item | Value | How we know |
|---|---|---|
| Serial for the RDK | `Rizon4-062157` | robot's own DDS topic names |
| Internal serial shown by Elements | `A02L-07-M2-062157` | Elements Studio log |
| Controller IP | `192.168.2.100` | ping, Studio connects to it |
| Laptop | `Ethernet 3`, static `192.168.2.110/24`, no gateway | ipconfig |
| Robot software | v3.9.3 | reported by Shyan from Elements; the robot's last update package is `FSP_v3.9.3`. Not read through the RDK. |
| Elements tool selected | another team's `Seat_Assembly_tool` | reported by Shyan. Expect a force offset until our handle is set as the tool. |
| Licence type | unknown | needs a connection or the Elements licence page |
| `K_x_nom` | unknown | needs a connection |
| Start pose (`tcp_pose`, `q`) | unknown | needs a connection |
| Wrench with nothing touching | unknown | needs a connection |

### Elements Studio 3.9.3 launch (works)

Runs on Shyan's laptop in WSL (Ubuntu 22.04, WSLg, mirrored networking) and its scanner finds the robot.
One click: `C:\Users\shyan\Desktop\Start Flexiv Studio.bat`, then REFRESH and Connect in the window. Command:

```
wsl -d Ubuntu-22.04 -u shyan -- bash -lc "~/flexiv/studio-3.9.3/run_studio.sh"
```

`run_studio.sh` does what Flexiv's own `run_FlexivElements.sh` would, without storing a sudo password:
`LD_LIBRARY_PATH=./lib`, `QT_QPA_PLATFORM_PLUGIN_PATH=./plugins`, `QT_QPA_PLATFORM=xcb`,
`QTWEBENGINE_DISABLE_SANDBOX=1`, then `./FlexivElementsStudio -p ubuntu_pc` (the other flags default to
`./specs_ui/`, `./user_data_ui/`, `./userDataTemplate/`). Flexiv's `setup_FlexivElements.sh` was not run.
The RDK cannot connect whether Studio is open or closed.

## 4. `robot/arm.py` and `robot/recover.py` against flexivrdk 1.7.0

From introspecting the installed 1.7.0 module (signatures and field lists). Not run against the robot.

| Call or field | In 1.7.0 | Verdict |
|---|---|---|
| `flexivrdk.Robot(serial)` | `Robot(robot_sn, network_interface_whitelist=[], verbose=True)` | OK (no `lite` argument in 1.7) |
| `fault()`, `operational()`, `Enable()`, `Stop()` | same | OK |
| `ClearFault()` | `ClearFault(timeout_sec=30) -> bool` | OK |
| `SwitchMode(Mode.NRT_CARTESIAN_MOTION_FORCE)` | exists | OK |
| `SwitchMode(Mode.NRT_PRIMITIVE_EXECUTION)` | exists | OK |
| **`SendCartesianMotionForce(pose, wrench, velocity, max_linear_vel, max_angular_vel, max_linear_acc, max_angular_acc)`** | `SendCartesianMotionForce(pose, wrench, max_linear_vel, max_angular_vel, max_linear_acc, max_angular_acc)` | **DIFFERENT. 1.7.0 has no `velocity` argument. `arm.py` line 297 to 299 passes 7 positional arguments and will raise `TypeError`.** |
| `SetCartesianImpedance(K_x)` | `SetCartesianImpedance(K_x, Z_x=[0.7]*6)` | OK |
| `SetMaxContactWrench([6 values])` | same, one list of 6 | OK |
| `ExecutePrimitive("ZeroFTSensor", dict())` | `ExecutePrimitive(primitive_name, input_params, block_until_started=True)` | Signature OK. Primitive name not checkable offline. |
| `primitive_states().get("terminated")` | returns a `dict` | Signature OK. The `"terminated"` key is not checkable offline. |
| `states().tcp_pose`, `.tcp_vel`, `.ext_wrench_in_world`, `.q` | all four fields exist | OK |
| `info().K_x_nom` | exists (also `license_type`, `software_ver`, `serial_num`, `model_name`) | OK |
| `flexivrdk.Tool`, `ToolParams.mass`, `.CoM` | exist: `Tool.Add/Switch/Update/Remove/exist/list/name/params` | OK (not used in `arm.py` today) |
| Missing in 1.7.0, present in 1.9 | `SetMaxContactTorque`, `SetJointInertiaScale`, `SendMultiCartesianMotionForce`, `SetTimelinessFailureLimit`, `actions`, `lite`; fields `RobotInfo.has_FT_sensor`, `RobotStates.timestamp`, `.temperature`, `.tau_interact` | not used by `arm.py` or `recover.py` |

## 5. What Kian must change

Status at 21:10 Swiss time: items 1 and 2 are already done on main (`robot/requirements.txt` has
`flexivrdk==1.7.*` and `numpy`; Shiv fixed `_send_pose` with Kian's OK). Items 3 to 5 are still open, and
the table in section 4 describes `arm.py` as it was before that fix.

1. **`robot/requirements.txt`** (new file): `flexivrdk==1.7.0` and `numpy`. The 1.7.0 wheel does not pull in
   numpy and `import flexivrdk` fails without it. There is a Python 3.12 Windows wheel. 1.7.0 is the only 1.7.x.
   This pin follows Flexiv's table (robot v3.9 with RDK v1.7); it is not proven by a connection yet.
2. **`robot/arm.py` `_send_pose`**: drop the third argument (`[0.0] * 6`, the velocity) so the call is
   `SendCartesianMotionForce(pose, [0.0]*6, max_linear_vel, MAX_ANGULAR_VEL, max_linear_acc, MAX_ANGULAR_ACC)`.
   Safer: pass the limits by keyword, which works on both 1.7 and 1.9. `robot/tests/test_arm_offline.py` line 197 unpacks 7 values (`pose, wrench, vel, max_lv, ...`) and needs the same change; its fake robot accepts any arguments, which is why the tests pass today.
3. **`robot/config.json`**: set `"serial": "Rizon4-062157"` and remove `"serial"` from `placeholders`.
   `start_pose` stays a placeholder until the arm connects. The format is already right
   (`tcp_pose` = x, y, z, qw, qx, qy, qz; `q` = 7 joint angles in rad), so the values from
   `states().tcp_pose` and `states().q` paste straight in:
   ```json
   "start_pose": { "tcp_pose": [x, y, z, qw, qx, qy, qz], "q": [q1, q2, q3, q4, q5, q6, q7] }
   ```
4. **Docs**: `robot/SETUP.md`, `robot/RUNBOOK.md` and `robot/recover.py` say "1.9.x". Change to 1.7.0.
5. **Once connected**: set our handle as the tool (not `Seat_Assembly_tool`) before zeroing or reading force.

## 6. Ready on Shyan's laptop

- `C:\venvs\flexiv17`: Python 3.12.10, `flexivrdk==1.7.0`, numpy. Use this for the arm.
- `C:\venvs\leukerbad`: project requirements, no `flexivrdk`. Offline tests: 256 passed.
- Read-only probe script (prints state, info, pose, joints and three wrench samples, writes JSON):
  `%TEMP%\flexiv_diag\read_state2.py`. Run: `C:\venvs\flexiv17\Scripts\python.exe read_state2.py Rizon4-062157`.
