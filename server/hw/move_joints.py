"""Slow joint-space move (MoveJ primitive) with monitoring. MOVES THE ARM.

    python -u -m server.hw.move_joints A2=-40 A4=90 --serial Rizon4-062157        # dry run, no motion
    python -u -m server.hw.move_joints A2=-40 A4=90 --serial Rizon4-062157 --go   # execute

Run it in your own terminal so Ctrl+C reaches it; the e-stop is the only instant stop.

Joints not named keep their current angle. Angles in degrees. Before moving, the predicted flange
path (the robot's own Jacobian integrated from the measured pose) is printed.

During the move it calls robot.Stop() on: a fault, external force changing more than --fmax N
(default 20) from the start of the move, any joint faster than --dqmax rad/s (default 0.2, a
backstop in case jntVelScale is ignored), any joint within 10 deg of a limit, Ctrl+C, or timeout.
Afterwards it prints pose, q, joint margins and three hands-off force readings.
"""
from __future__ import annotations

import math
import sys
import time

import numpy as np

from server.hw._common import connect_checked, flag, option

D, R = math.degrees, math.radians


def parse_targets(argv):
    t = {}
    for a in argv:
        if a[:1] == "A" and "=" in a:
            k, v = a[1:].split("=", 1)
            t[int(k) - 1] = float(v)
    return t


def predict(model, q_from, q_to, p0, n=400):
    qa, qb = np.radians(q_from), np.radians(q_to)
    p, pts = np.array(p0, float), [np.array(p0, float)]
    for i in range(n):
        q = qa + (qb - qa) * (i + 0.5) / n
        model.Update(list(q), [0.0] * 7)
        p = p + np.array(model.J("flange"))[:3] @ ((qb - qa) / n)
        pts.append(p.copy())
    return np.array(pts)


def margins(q_deg, qmin, qmax):
    return [min(q - D(lo), D(hi) - q) for q, lo, hi in zip(q_deg, qmin, qmax)]


def report_state(robot, info):
    s = robot.states()
    q = [D(x) for x in s.q]
    p = s.tcp_pose
    print(f"tcp_pose: {[round(x, 6) for x in p]}")
    print(f"  hand {p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f} m; distance from base axis {math.hypot(p[0], p[1]):.3f} m")
    print(f"q (deg): {[round(x, 1) for x in q]}")
    print(f"q (rad): {[round(x, 6) for x in s.q]}")
    print(f"margins to limits (deg): {[round(x, 1) for x in margins(q, info.q_min, info.q_max)]}")
    for i in range(3):
        if i:
            time.sleep(2)
        w = robot.states().ext_wrench_in_world
        print(f"empty force {i + 1}: {[round(x, 2) for x in w[:3]]} N  |F| {np.linalg.norm(w[:3]):.2f} N")


def main():
    import flexivrdk as f
    targets = parse_targets(sys.argv[1:])
    if not targets:
        sys.exit("give targets like A2=-40 A4=90")
    go = flag("--go")
    scale = int(option("--scale", "5"))
    fmax = float(option("--fmax", "20"))
    dqmax = float(option("--dqmax", "0.2"))
    timeout = float(option("--timeout", "240"))

    if go:
        robot, _, _ = connect_checked(require_tool="Flange")
    else:
        robot = f.Robot(option("--serial", "Rizon4-062157"))
        print("DRY RUN (no --go): nothing will move. operational:", robot.operational(),
              robot.operational_status() if hasattr(robot, "operational_status") else "",
              "fault:", robot.fault(), "tool:", f.Tool(robot).name())
    info = robot.info()
    s = robot.states()
    q0 = [D(x) for x in s.q]
    q1 = list(q0)
    for j, v in targets.items():
        q1[j] = v
    m1 = margins(q1, info.q_min, info.q_max)
    if min(m1) < 10:
        sys.exit(f"ABORT: target within 10 deg of a joint limit: {[round(x, 1) for x in m1]}")
    P = predict(f.Model(robot), q0, q1, s.tcp_pose[:3])
    r = np.hypot(P[:, 0], P[:, 1])
    dq = [b - a for a, b in zip(q0, q1)]
    print(f"start deg: {[round(x, 1) for x in q0]}")
    print(f"end   deg: {[round(x, 1) for x in q1]}")
    print(f"change   : {[round(x, 1) for x in dq]}  largest {max(map(abs, dq)):.1f} deg")
    print(f"predicted hand: start {np.round(P[0], 3)} end {np.round(P[-1], 3)}; "
          f"path z {P[:, 2].min():.3f}..{P[:, 2].max():.3f} m, r {r.min():.3f}..{r.max():.3f} m")
    call = {"target": f"JPos({[round(x, 2) for x in q1]})", "jntVelScale": scale}
    print(f"call: robot.ExecutePrimitive('MoveJ', {call})")
    if not go:
        return

    t0, reason, peak_dq = time.time(), None, 0.0
    try:
        robot.SwitchMode(f.Mode.NRT_PRIMITIVE_EXECUTION)
        w0 = np.array(robot.states().ext_wrench_in_world[:3])
        robot.ExecutePrimitive("MoveJ", {"target": f.JPos(q1, [0.0] * 6), "jntVelScale": scale})
        t0 = time.time()
        while True:
            time.sleep(0.02)
            st = robot.states()
            now, q = time.time(), np.array(st.q)
            vel = np.abs(np.array(st.dq))
            peak_dq = max(peak_dq, float(vel.max()))
            dF = float(np.linalg.norm(np.array(st.ext_wrench_in_world[:3]) - w0))
            mg = min(margins([D(x) for x in q], info.q_min, info.q_max))
            if robot.fault():
                reason = "fault"
            elif dF > fmax:
                reason = f"force change {dF:.1f} N > {fmax}"
            elif vel.max() > dqmax:
                reason = f"joint speed {vel.max():.3f} rad/s > {dqmax}"
            elif mg < 10:
                reason = f"joint within {mg:.1f} deg of a limit"
            elif now - t0 > timeout:
                reason = "timeout"
            if reason:
                break
            if int((now - t0) * 50) % 50 == 0:
                print(f"  t {now - t0:5.1f}s  dF {dF:5.1f} N  max dq {vel.max():.3f} rad/s  min margin {mg:5.1f} deg")
            if robot.primitive_states().get("reachedTarget") in (True, 1, "1", "true"):
                break
    except KeyboardInterrupt:
        reason = "Ctrl+C"
    except Exception as e:
        reason = f"error: {e!r}"
    finally:
        robot.Stop()
    print(f"STOPPED: {reason}" if reason else "reached target")
    print(f"time {time.time() - t0:.1f} s, peak joint speed {peak_dq:.3f} rad/s")
    time.sleep(1.0)
    report_state(robot, info)


if __name__ == "__main__":
    main()
