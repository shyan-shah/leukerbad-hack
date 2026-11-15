"""Show an exercise's path on the real arm with NOBODY touching it. MOVES THE ARM.

    python -u -m server.hw.trace_path reach            # dry run: prints the plan
    python -u -m server.hw.trace_path reach --go       # reach | push | pull | armtest

Same scripted motion as drift_check.py: straight line along the configured reach, 0.05 m/s,
nominal stiffness, orientation held, SetMaxContactWrench([30, 30, 30, 5, 5, 5]); robot.Stop() on a
fault, hand speed above 0.25 m/s, force above 25 N or the hand more than 3 cm from the commanded
point. Start pose, reach axis and sign come from robot/config.json; lengths from
software/exercises.py. Refuses unless fault-free, operational, IDLE, tool Flange and within 2 cm of
the start pose. Never calls Enable() or ClearFault(). 5 s countdown. Always ends with Stop().
This shows where the handle travels, not the forces of the exercise.
"""
from __future__ import annotations

import json
import math
import sys
import time

import numpy as np

from server.hw._common import CONFIG, connect_checked, flag, out_dir, positional
from server.hw.drift_check import CONTACT, DT, TRIP_FORCE, TRIP_SPEED, TRIP_TRACK, Trip
from server.hw.home_check import countdown

SPEED = 0.05

# (distance along the reach in m as a share of the exercise length, pause in s, what it shows)
PLANS = {
    "reach": [(1, 1.0, "far end of the reach"), (0, 1.0, "start"), (1, 1.0, "far end again"), (0, 1.0, "start")],
    "push": [(1, 1.0, "far end of the push"), (0, 1.0, "start")],
    "pull": [(1, 3.0, "far end: this is where the patient starts the row"), (0, 1.0, "start: this was the pull"),
             (1, 1.0, "far end again"), (0, 1.0, "home")],
    "armtest": [(0, 5.0, "no travel: the handle is held here while the patient pushes")],
}


def main() -> int:
    import flexivrdk as f
    from software.exercises import EXERCISES

    names = [a for a in positional() if a in PLANS]
    if len(names) != 1:
        sys.exit("give one of: reach, push, pull, armtest")
    name = names[0]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    goal = np.array(cfg["start_pose"]["tcp_pose"][:3], float)
    u = np.zeros(3)
    u[int(cfg["reach_axis"])] = -1.0 if float(cfg.get("reach_sign", 1)) < 0 else 1.0
    length = float(EXERCISES[name].reach_m) if name != "armtest" else 0.0
    plan = [(share * length, pause, label) for share, pause, label in PLANS[name]]
    far = goal + u * length
    print(f"{name}: start {np.round(goal, 3)}, far end {np.round(far, 3)}, length {length:.2f} m, "
          f"stops {[round(d, 2) for d, _, _ in plan]}")
    if not flag("--go"):
        print("DRY RUN: nothing moves.")
        return 0
    robot, _, k_nom = connect_checked(require_tool="Flange")
    start = [float(v) for v in robot.states().tcp_pose]
    p0 = np.array(start[:3])
    if np.linalg.norm(p0 - goal) > 0.02:
        print(f"ABORT: the hand is {np.linalg.norm(p0 - goal) * 100:.1f} cm from the start pose (limit 2 cm).")
        return 3
    rec, reason = [], None

    def send_and_check(target):
        robot.SendCartesianMotionForce(list(target) + start[3:7], [0.0] * 6, 0.15, 0.5, 0.3, 2.0)
        st = robot.states()
        pos = np.array(st.tcp_pose[:3])
        sp, fm = float(np.linalg.norm(st.tcp_vel[:3])), float(np.linalg.norm(st.ext_wrench_in_world[:3]))
        err = float(np.linalg.norm(pos - target))
        rec.append((*pos, sp, fm, err))
        if robot.fault():
            raise Trip("robot fault")
        if sp > TRIP_SPEED:
            raise Trip(f"speed {sp:.3f} m/s > {TRIP_SPEED}")
        if fm > TRIP_FORCE:
            raise Trip(f"force {fm:.1f} N > {TRIP_FORCE}")
        if err > TRIP_TRACK:
            raise Trip(f"hand {err * 100:.1f} cm from the commanded point")
        time.sleep(DT)

    countdown([])
    try:
        robot.SwitchMode(f.Mode.NRT_CARTESIAN_MOTION_FORCE)
        robot.SetMaxContactWrench(CONTACT)
        robot.SetCartesianImpedance(list(k_nom))
        d_now = 0.0
        for d, pause, label in plan:
            n = int(math.ceil(abs(d - d_now) / (SPEED * DT)))
            for i in range(1, n + 1):
                send_and_check(p0 + u * (d_now + (d - d_now) * i / n))
            d_now = d
            print(f"  at {d * 100:4.1f} cm: {label}", flush=True)
            for _ in range(int(pause / DT)):
                send_and_check(p0 + u * d_now)
    except Trip as e:
        reason = str(e)
    except KeyboardInterrupt:
        reason = "Ctrl+C"
    except Exception as e:
        reason = f"error: {e!r}"
    finally:
        robot.Stop()
    time.sleep(0.5)
    a = np.array(rec) if rec else np.zeros((1, 6))
    r = np.hypot(a[:, 0], a[:, 1])
    end = np.array(robot.states().tcp_pose[:3])
    out = dict(exercise=name, tripped=reason, x=[float(a[:, 0].min()), float(a[:, 0].max())],
               y=[float(a[:, 1].min()), float(a[:, 1].max())], z=[float(a[:, 2].min()), float(a[:, 2].max())],
               r_min=float(r.min()), r_max=float(r.max()), max_speed=float(a[:, 3].max()),
               max_force=float(a[:, 4].max()), max_track_mm=float(a[:, 5].max() * 1000),
               end_mm=float(np.linalg.norm(end - goal) * 1000))
    print(f"STOPPED: {reason}" if reason else "completed")
    print(f"flange path: x {out['x'][0]:.3f}..{out['x'][1]:.3f}, y {out['y'][0]:.3f}..{out['y'][1]:.3f}, "
          f"z {out['z'][0]:.3f}..{out['z'][1]:.3f} m; distance from the base axis {out['r_min']:.3f}..{out['r_max']:.3f} m")
    print(f"max speed {out['max_speed']:.3f} m/s, max empty force {out['max_force']:.2f} N, max tracking error "
          f"{out['max_track_mm']:.1f} mm, ended {out['end_mm']:.2f} mm from the start pose; "
          f"fault={robot.fault()} mode={robot.mode()}")
    (out_dir() / f"trace_{name}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0 if reason is None else 6


if __name__ == "__main__":
    sys.exit(main())
