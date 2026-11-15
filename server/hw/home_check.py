"""Check Arm.home(): move the flange 5 cm along the reach, then home() back. MOVES THE ARM.

    python -u -m server.hw.home_check          # dry run: prints the plan
    python -u -m server.hw.home_check --go     # execute (5 s countdown first)

Nobody touches the arm. The 5 cm move is a straight line at 0.05 m/s at nominal stiffness (as in
drift_check.py); then robot.Stop(), then robot.arm.Arm.home() to the start pose in
robot/config.json. Pass: ends within 3 mm of the configured start pose. Serial, start pose, reach
axis and sign come from robot/config.json. Never calls Enable() or ClearFault(); always ends with
Arm.close() (nominal stiffness restored, Stop()).
"""
from __future__ import annotations

import json
import math
import sys
import time

import numpy as np

from robot.arm import Limits
from server.hw._common import CONFIG, attach_arm, connect_checked, flag, out_dir
from server.hw.drift_check import CONTACT, DT, Trip, run_line  # noqa: F401  (same limits)

AWAY_M = 0.05
SPEED = 0.05


def countdown(lines: list[str], seconds: int = 5) -> None:
    for line in lines:
        print(line)
    for i in range(seconds, 0, -1):
        print(f"  starting in {i} s (e-stop or Ctrl+C to cancel)", flush=True)
        time.sleep(1.0)


def main() -> int:
    import flexivrdk as f

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    goal = np.array(cfg["start_pose"]["tcp_pose"][:3], float)
    u = np.zeros(3)
    u[int(cfg["reach_axis"])] = -1.0 if float(cfg.get("reach_sign", 1)) < 0 else 1.0
    go = flag("--go")
    if not go:
        print(f"DRY RUN: would move {AWAY_M * 100:.0f} cm along {np.round(u, 0)} from the current pose at "
              f"{SPEED} m/s, then Arm.home() to {np.round(goal, 4)}; pass = within 3 mm.")
        return 0
    robot, rdk, k_nom = connect_checked(require_tool="Flange")
    st = robot.states()
    p0 = np.array(st.tcp_pose[:3])
    d0 = float(np.linalg.norm(p0 - goal))
    print(f"hand {np.round(p0, 4)}, {d0 * 1000:.1f} mm from the configured start pose")
    if d0 > 0.02:
        print("ABORT: the hand is more than 2 cm from the start pose; this check starts from it.")
        return 3
    countdown([f"Home check: the flange moves {AWAY_M * 100:.0f} cm along the reach ({np.round(u, 0)}) at {SPEED} m/s, "
               "nominal stiffness,", "then Arm.home() brings it back at 0.05 m/s. Nobody touches the arm. About 15 s."])
    result, reason, arm = dict(start=p0.tolist(), goal=goal.tolist()), None, None
    try:
        robot.SwitchMode(f.Mode.NRT_CARTESIAN_MOTION_FORCE)
        robot.SetMaxContactWrench(CONTACT)
        robot.SetCartesianImpedance(list(k_nom))
        start = [float(v) for v in robot.states().tcp_pose]
        n = int(math.ceil(AWAY_M / (SPEED * DT)))
        for i in range(1, n + 150):                       # ramp, then 1.5 s settle
            d = min(i / n, 1.0) * AWAY_M
            target = np.array(start[:3]) + u * d
            robot.SendCartesianMotionForce(list(target) + start[3:7], [0.0] * 6, 0.08, 0.5, 0.3, 2.0)
            s = robot.states()
            if robot.fault():
                raise Trip("robot fault")
            if np.linalg.norm(s.tcp_vel[:3]) > 0.25 or np.linalg.norm(s.ext_wrench_in_world[:3]) > 25.0 \
                    or np.linalg.norm(np.array(s.tcp_pose[:3]) - target) > 0.03:
                raise Trip("speed, force or tracking limit during the 5 cm move")
            time.sleep(DT)
        away = np.array(robot.states().tcp_pose[:3])
        result["away_mm"] = float(np.linalg.norm(away - goal) * 1000)
        print(f"moved away: hand {np.round(away, 4)}, {result['away_mm']:.1f} mm from the start pose")
        robot.Stop()
        time.sleep(0.5)
        arm = attach_arm(Limits(), robot, rdk, k_nom)
        t0 = time.time()
        arm.home()
        result["home_s"] = round(time.time() - t0, 1)
        time.sleep(0.5)
        end = np.array(robot.states().tcp_pose[:3])
        result["end_mm"] = float(np.linalg.norm(end - goal) * 1000)
        result["pass"] = result["end_mm"] < 3.0
        print(f"home() took {result['home_s']} s; ended {result['end_mm']:.2f} mm from the start pose "
              f"(pass < 3 mm) -> {'PASS' if result['pass'] else 'FAIL'}")
    except Trip as e:
        reason = str(e)
    except KeyboardInterrupt:
        reason = "Ctrl+C"
    except Exception as e:
        reason = f"error: {e!r}"
    finally:
        try:
            if arm is not None:
                arm.close()
        finally:
            robot.Stop()
    result["tripped"] = reason
    time.sleep(0.5)
    print(f"STOPPED: {reason}" if reason else "completed")
    print(f"after: fault={robot.fault()} mode={robot.mode()} operational={robot.operational()} "
          f"tcp {np.round(robot.states().tcp_pose[:3], 4)}")
    (out_dir() / "home_check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if reason is None and result.get("pass") else 6


if __name__ == "__main__":
    sys.exit(main())
