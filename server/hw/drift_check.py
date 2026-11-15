"""Empty-force drift along the reach line. MOVES THE ARM (straight line, slow, nominal stiffness).

    python -u -m server.hw.drift_check --axis x --sign -1 --serial Rizon4-062157          # dry run
    python -u -m server.hw.drift_check --axis x --sign -1 --serial Rizon4-062157 --go     # execute

Nobody touches the arm. Sequence: ZeroFTSensor at the start (skip with --no-zero), then the flange
moves --length m (default 0.30) along the world axis at --speed (default 0.05 m/s) with the
orientation held, pausing every --step m (default 0.05) to read the empty force, then back the same
way, then reads again at the start and 30 s later.

Like Arm.home(): NRT_CARTESIAN_MOTION_FORCE at nominal stiffness (K_x_nom), a streamed target ramp,
SetMaxContactWrench([30, 30, 30, 5, 5, 5]). Never calls Enable() or ClearFault(); refuses unless
fault-free, operational, IDLE, tool Flange. Stops with robot.Stop() on: fault, hand speed above
0.25 m/s, force above 25 N, hand more than 3 cm from the commanded point, Ctrl+C, or timeout.
Always ends with Stop(). Stiffness is never changed from nominal.
Result: server/hw/out/drift_check.json.
"""
from __future__ import annotations

import json
import math
import sys
import time

import numpy as np

from server.hw._common import connect_checked, flag, option, out_dir

DT = 0.01
TRIP_SPEED = 0.25      # m/s
TRIP_FORCE = 25.0      # N, estimated external force with nothing touching
TRIP_TRACK = 0.03      # m between the hand and the commanded point
PAUSE_S = 2.0          # at each reading point (the last 0.6 s is averaged)
CONTACT = [30.0, 30.0, 30.0, 5.0, 5.0, 5.0]


class Trip(Exception):
    pass


def run_line(robot, send, start_pose, u, length, step, speed, log=print, sleep=time.sleep, clock=time.time):
    """Out and back along unit vector u from start_pose. Returns the list of readings."""
    p0 = np.array(start_pose[:3], float)
    quat = list(start_pose[3:7])
    readings, moving_peak = [], [0.0]

    def check(target):
        st = robot.states()
        if robot.fault():
            raise Trip("robot fault")
        pos = np.array(st.tcp_pose[:3])
        speed_now = float(np.linalg.norm(st.tcp_vel[:3]))
        fmag = float(np.linalg.norm(st.ext_wrench_in_world[:3]))
        if speed_now > TRIP_SPEED:
            raise Trip(f"speed {speed_now:.3f} m/s > {TRIP_SPEED}")
        if fmag > TRIP_FORCE:
            raise Trip(f"force {fmag:.1f} N > {TRIP_FORCE}")
        err = float(np.linalg.norm(pos - target))
        if err > TRIP_TRACK:
            raise Trip(f"hand {err * 100:.1f} cm from the commanded point")
        return st, fmag

    def hold(target, seconds, label, d):
        w, n = [], int(seconds / DT)
        for i in range(n):
            send(list(target) + quat)
            st, _ = check(target)
            if i >= n - 60:
                w.append(st.ext_wrench_in_world[:3])
            sleep(DT)
        w = np.mean(w, axis=0)
        pos = np.array(robot.states().tcp_pose[:3])
        r = dict(label=label, d_m=round(d, 3), force=[round(float(x), 2) for x in w],
                 f_n=round(float(np.linalg.norm(w)), 2), pos=[round(float(x), 4) for x in pos],
                 off_line_mm=round(float(np.linalg.norm((pos - p0) - np.dot(pos - p0, u) * u)) * 1000, 1),
                 moving_peak_n=round(moving_peak[0], 2), t=round(clock(), 1))
        readings.append(r)
        log(f"  {label:>10} d {d * 100:5.1f} cm  F {r['force']} |F| {r['f_n']:.2f} N  "
            f"(peak while moving there {r['moving_peak_n']:.2f} N)  off line {r['off_line_mm']} mm")
        moving_peak[0] = 0.0

    def move(d_from, d_to):
        n = max(1, int(math.ceil(abs(d_to - d_from) / (speed * DT))))
        for i in range(1, n + 1):
            d = d_from + (d_to - d_from) * i / n
            target = p0 + u * d
            send(list(target) + quat)
            _, fmag = check(target)
            moving_peak[0] = max(moving_peak[0], fmag)
            sleep(DT)

    stops = [round(k * step, 6) for k in range(int(round(length / step)) + 1)]
    hold(p0, PAUSE_S, "out", 0.0)
    for a, b in zip(stops, stops[1:]):
        move(a, b)
        hold(p0 + u * b, PAUSE_S, "out", b)
    for a, b in zip(stops[::-1], stops[::-1][1:]):
        move(a, b)
        hold(p0 + u * b, PAUSE_S, "back", b)
    return readings


def main() -> int:
    import flexivrdk as f

    go = flag("--go")
    axis = "xyz".index(option("--axis", "x"))
    sign = -1.0 if float(option("--sign", "1")) < 0 else 1.0
    length, step, speed = float(option("--length", "0.30")), float(option("--step", "0.05")), float(option("--speed", "0.05"))
    if not (0 < length <= 0.35 and 0 < step <= length and 0 < speed <= 0.05):
        sys.exit("limits: length <= 0.35 m, step <= length, speed <= 0.05 m/s")
    u = np.zeros(3)
    u[axis] = sign

    if go:
        robot, _, k_nom = connect_checked(require_tool="Flange")
    else:
        robot = f.Robot(option("--serial", "Rizon4-062157"))
        k_nom = [float(v) for v in robot.info().K_x_nom]
        print("DRY RUN (no --go): nothing will move. operational:", robot.operational(), "fault:", robot.fault(),
              "mode:", robot.mode(), "tool:", f.Tool(robot).name())
    st = robot.states()
    start = [float(v) for v in st.tcp_pose]
    end = np.array(start[:3]) + u * length
    w = np.array(st.ext_wrench_in_world[:3])
    print(f"start {np.round(start[:3], 3)} -> end {np.round(end, 3)} (world {'xyz'[axis]}, sign {sign:+.0f}), "
          f"{length:.2f} m at {speed:.2f} m/s, reading every {step * 100:.0f} cm, K_x_nom {k_nom[:3]}")
    print(f"distance from base axis: start {math.hypot(start[0], start[1]):.3f} m, end {math.hypot(end[0], end[1]):.3f} m; "
          f"empty force now {np.round(w, 2)} |F| {np.linalg.norm(w):.2f} N")
    if not go:
        return 0

    result = dict(start_pose=start, q_start=[float(v) for v in st.q], axis="xyz"[axis], sign=sign,
                  length=length, speed=speed, zeroed=False, tripped=None)
    reason = None
    try:
        if not flag("--no-zero"):
            robot.SwitchMode(f.Mode.NRT_PRIMITIVE_EXECUTION)
            robot.ExecutePrimitive("ZeroFTSensor", dict())
            t0 = time.time()
            while time.time() - t0 < 20:
                time.sleep(0.1)
                if robot.primitive_states().get("terminated") in (True, 1, "1", "true") or \
                        (time.time() - t0 > 1.0 and not robot.busy()):
                    break
            else:
                raise Trip("ZeroFTSensor did not terminate in 20 s")
            result["zeroed"] = True
            time.sleep(0.5)
            w = np.array(robot.states().ext_wrench_in_world[:3])
            print(f"zeroed: empty force {np.round(w, 2)} |F| {np.linalg.norm(w):.2f} N")
        robot.SwitchMode(f.Mode.NRT_CARTESIAN_MOTION_FORCE)
        robot.SetMaxContactWrench(CONTACT)
        robot.SetCartesianImpedance(list(k_nom))
        start = [float(v) for v in robot.states().tcp_pose]      # hold exactly where it is now

        def send(pose):
            robot.SendCartesianMotionForce(pose, [0.0] * 6, 0.08, 0.5, 0.3, 2.0)

        result["readings"] = run_line(robot, send, start, u, length, step, speed)
        print("back at the start; waiting 30 s, hands off")
        p0 = np.array(start[:3])
        t_end = time.time() + 30.0
        while time.time() < t_end:
            send(start)
            if robot.fault():
                raise Trip("robot fault")
            time.sleep(DT)
        ws = []
        for _ in range(60):
            send(start)
            ws.append(robot.states().ext_wrench_in_world[:3])
            time.sleep(DT)
        w = np.mean(ws, axis=0)
        pos = np.array(robot.states().tcp_pose[:3])
        result["after_30s"] = dict(force=[round(float(x), 2) for x in w], f_n=round(float(np.linalg.norm(w)), 2),
                                   end_mm=round(float(np.linalg.norm(pos - p0)) * 1000, 2))
        print(f"  30 s later  F {result['after_30s']['force']} |F| {result['after_30s']['f_n']:.2f} N  "
              f"{result['after_30s']['end_mm']} mm from the start")
    except Trip as e:
        reason = str(e)
    except KeyboardInterrupt:
        reason = "Ctrl+C"
    except Exception as e:
        reason = f"error: {e!r}"
    finally:
        robot.Stop()
    result["tripped"] = reason
    time.sleep(1.0)
    st = robot.states()
    result["end_pose"] = [float(v) for v in st.tcp_pose]
    result["q_end"] = [float(v) for v in st.q]
    print(f"STOPPED: {reason}" if reason else "completed")
    print(f"after: fault={robot.fault()} mode={robot.mode()} operational={robot.operational()} "
          f"tcp {np.round(st.tcp_pose[:3], 4)}")
    rs = result.get("readings", [])
    if rs:
        worst = max(rs, key=lambda r: r["f_n"])
        peak = max(r["moving_peak_n"] for r in rs)
        print(f"standing readings: worst {worst['f_n']:.2f} N at {worst['d_m'] * 100:.0f} cm ({worst['label']}); "
              f"peak while moving {peak:.2f} N; limit asked for: 3 N")
        result["worst_standing_n"], result["peak_moving_n"] = worst["f_n"], peak
    (out_dir() / "drift_check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if reason is None else 6


if __name__ == "__main__":
    sys.exit(main())
