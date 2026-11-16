# robot/: the safety layer between our software and the Flexiv Rizon 4

`arm.py` is the **only** code in the project that talks to the robot (Flexiv RDK 1.7, Ethernet). Every limit lives here, below everything else, so no caller can override it.

| File | What it is |
|---|---|
| `arm.py` | `Arm`: connect, zero, home, compliant mode, stiffness, targets. Clamps (stiffness, distance from the hand, workspace box), trips (speed, force, leaving the box), watchdog, stiffness mapped onto the tool axes |
| `config.json` | Robot serial, start pose, reach direction, measured on the arm |
| `RUNBOOK.md` | Cold start, faults and recovery, shutdown, who holds the e-stop |
| `SAFETY.md` | Safety checks and results, including the staged high-force test |
| `TUNING.md` | Measured friction, stiffness and damping, recommended values |
| `safety_check.py`, `test_limits_stage.py` | Interactive on-arm safety checks (each motion waits for Enter) |
| `recover.py`, `read_tool_force.py`, `tune.py` | Fault recovery, read-only force check, tuning measurements |
| `tool_handle.md` | Mounting the printed handle and registering it as a tool |
| `tests/` | Offline tests (no robot needed) |

Key limits: 600 N/m stiffness × 5 cm anchor distance = 30 N maximum commanded pull; 0.15 m/s commanded speed; trips at 0.40 m/s or 40 N; ±35 cm × ±10 cm workspace box; 0.2 s watchdog.
