"""Run Flexiv's ZeroFTSensor primitive once and report the empty force before and after.

    python -u -m server.hw.zero_ft --serial Rizon4-062157          # dry run: reads only
    python -u -m server.hw.zero_ft --serial Rizon4-062157 --go     # runs the primitive

COMMANDS THE ROBOT (mode switch + primitive) but commands no motion. The robot must be still and
NOTHING may touch it: whatever load is on the arm at that moment becomes the new zero.

Never calls Enable() or ClearFault(); with --go it refuses unless the arm is fault-free,
operational, in IDLE and the tool is Flange. Always ends with Stop() (back to IDLE).
This Rizon 4 has no wrist sensor (ft_sensor_raw is all zeros): the force is estimated from the
joint torque sensors, so this script also prints the per-joint external torque (tau_ext).
"""
from __future__ import annotations

import sys
import time

import numpy as np

from server.hw._common import connect_checked, flag, option

TIMEOUT_S = 20.0


def read(robot, label, n=3, gap=2.0):
    out = []
    for i in range(n):
        if i:
            time.sleep(gap)
        w, te = [], []
        for _ in range(20):                      # 0.4 s average
            s = robot.states()
            w.append(s.ext_wrench_in_world[:3])
            te.append(s.tau_ext)
            time.sleep(0.02)
        w, te = np.mean(w, axis=0), np.mean(te, axis=0)
        out.append(w)
        print(f"{label} {i + 1}: F {np.round(w, 2)} N  |F| {np.linalg.norm(w):.2f} N   tau_ext {np.round(te, 2)} Nm")
    return np.array(out)


def main() -> int:
    import flexivrdk as f

    go = flag("--go")
    if go:
        robot, _, _ = connect_checked(require_tool="Flange")
    else:
        robot = f.Robot(option("--serial", "Rizon4-062157"))
        print("DRY RUN (no --go): reads only. operational:", robot.operational(), "fault:", robot.fault(),
              "mode:", robot.mode(), "tool:", f.Tool(robot).name())
    q0 = np.array(robot.states().q)
    before = read(robot, "before")
    if not go:
        return 0

    reason, t0 = None, time.time()
    try:
        robot.SwitchMode(f.Mode.NRT_PRIMITIVE_EXECUTION)
        robot.ExecutePrimitive("ZeroFTSensor", dict())
        t0 = time.time()
        while True:
            time.sleep(0.1)
            ps = robot.primitive_states()
            el = time.time() - t0
            if robot.fault():
                reason = "fault"
                break
            if ps.get("terminated") in (True, 1, "1", "true"):
                break
            if el > 1.0 and not robot.busy():
                break
            if el > TIMEOUT_S:
                reason = f"not terminated after {TIMEOUT_S:.0f} s (primitive_states {dict(ps)})"
                break
    except KeyboardInterrupt:
        reason = "Ctrl+C"
    except Exception as e:                       # e.g. the primitive is not supported on this arm
        reason = f"error: {e!r}"
    finally:
        robot.Stop()
    print(f"ZeroFTSensor: {'FAILED: ' + reason if reason else 'terminated'} after {time.time() - t0:.1f} s")
    time.sleep(1.0)
    print(f"after: fault={robot.fault()} mode={robot.mode()} operational={robot.operational()} "
          f"joints moved {np.degrees(np.abs(np.array(robot.states().q) - q0)).max():.3f} deg")
    after = read(robot, "after ")
    print(f"|F| before {np.linalg.norm(before.mean(axis=0)):.2f} N -> after {np.linalg.norm(after.mean(axis=0)):.2f} N")
    return 0 if reason is None else 4


if __name__ == "__main__":
    sys.exit(main())
