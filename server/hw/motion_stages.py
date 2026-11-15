"""Staged first-motion test (stages 1 to 4) on top of robot/arm.py. MOVES THE ARM.

    python -m server.hw.motion_stages <1|2|3|4> [--serial Rizon4-062157] [--axis x|y] [--sim] [--force-trip]

  1  HOLD        5 s at nominal stiffness, expect no motion (pass: drift under 2 mm)
  2  TINY MOVE   2 cm towards the base at 0.03 m/s and back, 600 N/m (pass: ends within 3 mm)
  3  SOFT HOLD   20 s at 300 N/m; push the flange about 2 cm by hand and let go (pass: back within 5 mm)
  4  FREE AXIS   20 s with 0 N/m on the reach axis (reach_axis in robot/config.json, or --axis x|y),
                 500 N/m on the others; slide it by hand

Safety, enforced here on top of Arm's own clamps, trips and watchdog:
  - never calls Enable() or ClearFault(); aborts unless no fault, operational, IDLE, tool Flange
  - Limits: 0.05 m/s, 0.3 m/s^2, k <= 600 N/m (stage 1 only: nominal), SetMaxContactWrench [30,30,30,5,5,5]
  - commanded targets at most 3 cm from the start
  - trips -> arm.stop() = robot.Stop(): speed > 0.25 m/s, force change from baseline > 25 N,
    hand outside a +/-5 cm box
  - hard time limit; normal exit restores K_x_nom (Arm.close) then Stop()
A running stage cannot be stopped from the keyboard of another terminal: the E-STOP is the real stop.
--sim runs against software/sim_arm.py (no robot). --force-trip (use with --sim) provokes a trip.
Results: server/hw/out/stage<N>.json and .csv.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import csv  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

from robot.arm import Limits  # noqa: E402
from server.hw._common import attach_arm, connect_checked, flag, option, out_dir, positional, sim_arm  # noqa: E402

TRIP_SPEED = 0.25      # m/s
TRIP_DFORCE = 25.0     # N from baseline
BOX = 0.05             # m
MAX_MOVE = 0.03        # m, commanded target distance from start
DT = 0.01

STAGE_CFG = {
    1: dict(name="HOLD at nominal stiffness", dur=5.0, k_hold=10000.0, k_max=10000.0),
    2: dict(name="TINY MOVE 2 cm towards base", dur=None, k_hold=600.0, k_max=600.0),
    3: dict(name="SOFT HOLD 300 N/m", dur=20.0, k_hold=300.0, k_max=600.0),
    4: dict(name="FREE AXIS (0 N/m on one axis, 500 on the others)", dur=20.0, k_hold=300.0, k_max=600.0),
}


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def run(stage: int, sim: bool, force_trip: bool, axis: str | None = None) -> dict:
    cfg = STAGE_CFG[stage]
    limits = Limits(k_max=cfg["k_max"], k_hold=cfg["k_hold"], max_lead_m=0.05,
                    max_linear_vel=0.05, max_linear_acc=0.3, trip_speed=TRIP_SPEED, trip_force=40.0,
                    max_contact_n=30.0, max_contact_nm=5.0, watchdog_s=0.2, box_half_m=(BOX, BOX, BOX))
    if sim:
        arm, robot, k_nom = sim_arm(limits), None, [10000.0] * 3 + [1500.0] * 3
    else:
        robot, rdk, k_nom = connect_checked(require_tool="Flange")
        arm = attach_arm(limits, robot, rdk, k_nom)

    rows, result = [], dict(stage=stage, name=cfg["name"], sim=sim, tripped=None)
    tripped = [None]
    done = threading.Event()

    def hard_stop(reason):
        if tripped[0] is None:
            tripped[0] = reason
        try:
            arm.stop()
        except Exception as e:
            print("arm.stop() raised:", repr(e))

    budget = (cfg["dur"] or 12.0) + 20.0

    def deadline():      # whatever happens, Stop() and exit
        if not done.wait(budget):
            print("HARD DEADLINE reached -> Stop()")
            hard_stop("hard deadline")
            os._exit(5)
    threading.Thread(target=deadline, daemon=True).start()

    try:
        acc, n = [0.0, 0.0, 0.0], 0                      # 1 s force baseline, nothing touching
        t_end = time.monotonic() + 1.0
        while time.monotonic() < t_end:
            acc = [a + f for a, f in zip(acc, arm.get_state().force)]
            n += 1
            time.sleep(DT)
        base = [a / n for a in acc]
        p0 = arm.get_state().pos
        r = math.hypot(p0[0], p0[1])
        to_base = (-p0[0] / r, -p0[1] / r, 0.0)
        # stage 4 frees the session's reach axis (robot/config.json), not "towards base"
        free_axis = "xy".index(axis) if axis else int(getattr(arm, "reach_axis", 0))
        print(f"start pos {[round(v, 4) for v in p0]}  baseline force {[round(v, 2) for v in base]} N "
              f"(|F| {norm(base):.2f})  towards-base {[round(v, 3) for v in to_base]}")
        result.update(start_pos=p0, baseline=base, to_base=to_base)

        arm.start_compliance()     # SwitchMode + SetMaxContactWrench + hold the current pose at k_hold
        start = arm.start_pos
        t0 = time.monotonic()
        if stage == 4:
            k = [500.0, 500.0, 500.0]
            k[free_axis] = 0.0
            arm.set_stiffness(*k)
            result.update(free_axis="xyz"[free_axis], stiffness=k)
        t_out = 0.02 / 0.03
        dur = cfg["dur"] if cfg["dur"] else (2.0 * t_out + 1.0 + 2.0)   # out, pause, back, settle
        next_tick = t0
        while True:
            t = time.monotonic() - t0
            if t >= dur:
                break
            st = arm.get_state()
            d = [p - s for p, s in zip(st.pos, start)]
            df = [f - b for f, b in zip(st.force, base)]
            speed = norm(st.vel)
            if stage == 2:
                if t < t_out:
                    a = 0.03 * t
                elif t < t_out + 1.0:
                    a = 0.02
                elif t < 2 * t_out + 1.0:
                    a = 0.02 - 0.03 * (t - t_out - 1.0)
                else:
                    a = 0.0
                if force_trip and t > 0.3:
                    a = 0.2
                a = min(max(a, 0.0), 1.0 if force_trip else MAX_MOVE)
                target = tuple(s + a * u for s, u in zip(start, to_base))
            elif stage == 4:
                target = list(start)
                target[free_axis] = st.pos[free_axis]      # free axis: the target rides on the hand
                target = tuple(target)
            else:
                target = tuple(start)
            rows.append([round(t, 4), *st.pos, *st.vel, *st.force, *target, st.mode])
            reason = None
            if st.mode != "compliant":
                reason = f"arm left compliant mode: {st.mode} / {st.fault}"
            elif speed > TRIP_SPEED:
                reason = f"speed {speed:.3f} m/s > {TRIP_SPEED}"
            elif norm(df) > TRIP_DFORCE:
                reason = f"force change {norm(df):.1f} N > {TRIP_DFORCE}"
            elif max(abs(x) for x in d) > BOX:
                reason = f"hand {max(abs(x) for x in d) * 100:.1f} cm from start, outside +/-{BOX * 100:.0f} cm box"
            if reason:
                print("TRIP:", reason)
                hard_stop(reason)
                break
            arm.set_target(target)
            next_tick += DT
            sl = next_tick - time.monotonic()
            if sl > 0:
                time.sleep(sl)
            else:
                next_tick = time.monotonic()
    except KeyboardInterrupt:
        hard_stop("KeyboardInterrupt")
    except Exception as e:
        print("EXCEPTION:", repr(e))
        hard_stop(f"exception {e!r}")
    finally:
        result["tripped"] = tripped[0]
        if tripped[0] is not None and robot is not None:
            try:   # after Stop() the robot is in IDLE; restoring impedance may be refused there
                robot.SetCartesianImpedance(k_nom)
                result["k_nom_restored"] = True
                print("K_x_nom restored after trip")
            except Exception as e:
                result["k_nom_restored"] = False
                print("K_x_nom restore after trip refused:", repr(e)[:200])
        try:
            arm.close()   # normal path: hold -> SetCartesianImpedance(K_x_nom) -> Stop()
            if tripped[0] is None:
                result["k_nom_restored"] = True
        except Exception as e:
            print("arm.close() raised:", repr(e))
        done.set()

    analyse(stage, rows, result)
    tag = f"stage{stage}{'_sim' if sim else ''}"
    with open(out_dir() / f"{tag}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow("t px py pz vx vy vz fx fy fz tx ty tz mode".split())
        w.writerows(rows)
    (out_dir() / f"{tag}.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    if robot is not None:
        time.sleep(0.5)
        print(f"after: fault={robot.fault()} mode={robot.mode()} operational={robot.operational()}")
    return result


def analyse(stage: int, rows: list, result: dict) -> None:
    if not rows or "start_pos" not in result:
        print("no samples")
        return
    start, base, u = result["start_pos"], result["baseline"], result["to_base"]
    P = [r[1:4] for r in rows]
    V = [r[4:7] for r in rows]
    F = [[f - b for f, b in zip(r[7:10], base)] for r in rows]
    T = [r[10:13] for r in rows]
    t = [r[0] for r in rows]
    dist = [math.dist(p, start) for p in P]
    result.update(samples=len(rows), duration=t[-1], rate_hz=len(rows) / max(t[-1], 1e-6),
                  max_dist_mm=max(dist) * 1000, max_speed=max(norm(v) for v in V),
                  max_dforce=max(norm(f) for f in F), end_dist_mm=dist[-1] * 1000)
    print(f"samples {len(rows)} over {t[-1]:.2f} s ({result['rate_hz']:.0f} Hz); max speed "
          f"{result['max_speed']:.3f} m/s; max force change {result['max_dforce']:.2f} N; tripped: {result['tripped']}")
    ok = result["tripped"] is None
    if stage == 1:
        result["pass"] = ok and result["max_dist_mm"] < 2.0
        print(f"STAGE 1: max drift {result['max_dist_mm']:.3f} mm (pass < 2 mm) -> {'PASS' if result['pass'] else 'FAIL'}")
    elif stage == 2:
        along = [sum((p[i] - start[i]) * u[i] for i in range(3)) for p in P]
        cmd = [sum((tg[i] - start[i]) * u[i] for i in range(3)) for tg in T]
        err = [abs(a - c) for a, c in zip(along, cmd)]
        lateral = [math.sqrt(max(d * d - a * a, 0.0)) for d, a in zip(dist, along)]
        tail = [d for d, tt in zip(dist, t) if tt > t[-1] - 0.5]
        end_mm = sum(tail) / len(tail) * 1000
        result.update(max_along_mm=max(along) * 1000, max_track_err_mm=max(err) * 1000,
                      mean_track_err_mm=sum(err) / len(err) * 1000, max_lateral_mm=max(lateral) * 1000,
                      end_mm=end_mm)
        result["pass"] = ok and end_mm < 3.0
        print(f"STAGE 2: reached {result['max_along_mm']:.1f} mm of 20 mm towards base; tracking error max "
              f"{result['max_track_err_mm']:.1f} mm, mean {result['mean_track_err_mm']:.1f} mm; lateral max "
              f"{result['max_lateral_mm']:.1f} mm; end {end_mm:.2f} mm from start (pass < 3 mm) -> "
              f"{'PASS' if result['pass'] else 'FAIL'}")
    elif stage == 3:
        i = max(range(len(rows)), key=lambda j: dist[j])
        k = 300.0
        fpk, dpk = norm(F[i]), dist[i]
        tail = [d for d, tt in zip(dist, t) if tt > t[-1] - 1.0]
        end_mm = sum(tail) / len(tail) * 1000
        ratio = fpk / (k * dpk) if dpk > 1e-4 else float("nan")
        # per axis: N per m at the peak (only where that axis moved over 5 mm), and where it ended
        d_pk = [P[i][j] - start[j] for j in range(3)]
        n_tail = max(1, len(tail))
        end_axis_mm = [sum(p[j] - start[j] for p in P[-n_tail:]) / n_tail * 1000 for j in range(3)]
        k_axis = [abs(F[i][j] / d_pk[j]) if abs(d_pk[j]) > 0.005 else None for j in range(3)]
        result.update(peak_disp_mm=dpk * 1000, force_at_peak=fpk, expected_force=k * dpk, ratio=ratio,
                      peak_force=max(norm(f) for f in F), end_mm=end_mm,
                      peak_disp_axis_mm=[v * 1000 for v in d_pk], force_at_peak_axis=list(F[i]),
                      n_per_m_axis=k_axis, end_axis_mm=end_axis_mm)
        result["pass"] = ok and end_mm < 5.0
        print("STAGE 3 per axis (x, y, z): displacement at peak "
              f"{[round(v * 1000, 1) for v in d_pk]} mm; force there {[round(v, 2) for v in F[i]]} N; "
              f"measured N/m {[None if v is None else round(v) for v in k_axis]} (commanded {k:.0f}); "
              f"return error {[round(v, 2) for v in end_axis_mm]} mm")
        print(f"STAGE 3: peak displacement {dpk * 1000:.1f} mm at t={t[i]:.1f} s; force there {fpk:.2f} N vs "
              f"k*d = {k * dpk:.2f} N (ratio {ratio:.2f}); peak force {result['peak_force']:.2f} N; "
              f"end {end_mm:.2f} mm from start (pass < 5 mm) -> {'PASS' if result['pass'] else 'FAIL'}")
    elif stage == 4:
        ax = "xyz".index(result["free_axis"])
        others = [j for j in range(3) if j != ax]
        travel = [p[ax] - start[ax] for p in P]
        moving = [abs(F[j][ax]) for j in range(len(rows)) if abs(V[j][ax]) > 0.01]
        result.update(free_travel_min_mm=min(travel) * 1000, free_travel_max_mm=max(travel) * 1000,
                      drag_mean_n=(sum(moving) / len(moving)) if moving else None,
                      drag_peak_n=max(moving) if moving else None,
                      other_axes_max_mm=max(abs(p[j] - start[j]) for p in P for j in others) * 1000,
                      end_free_mm=travel[-1] * 1000)
        result["pass"] = ok
        print(f"STAGE 4: free axis {result['free_axis']}; travel {result['free_travel_min_mm']:.1f} .. "
              f"{result['free_travel_max_mm']:.1f} mm; drag while moving mean {result['drag_mean_n']} N peak "
              f"{result['drag_peak_n']} N; other axes max {result['other_axes_max_mm']:.1f} mm; ended at "
              f"{result['end_free_mm']:.1f} mm -> {'PASS' if result['pass'] else 'FAIL (tripped)'}")


def main() -> int:
    pos = positional()
    if not pos or pos[0] not in ("1", "2", "3", "4"):
        print(__doc__)
        return 1
    axis = option("--axis")
    if axis not in (None, "x", "y"):
        print("--axis must be x or y")
        return 1
    result = run(int(pos[0]), flag("--sim"), flag("--force-trip"), axis)
    return 0 if result.get("tripped") is None else 6


if __name__ == "__main__":
    sys.exit(main())
