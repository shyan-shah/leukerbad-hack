"""Continuous translation-only motion for videos (orientation locked), on top of robot/arm.py. MOVES THE ARM.

    python -m server.hw.demo_motion [--seconds 240] [--scale 1.0] [--serial Rizon4-062157] [--sim]

Pattern, relative to where the flange is when the script starts, in (inward = towards the base,
lateral, up): inward 3..11 cm, lateral +/-10 cm, up 2..12 cm. It never goes further out or lower
than the start, ramps in and out over 6 s, and returns to the start.
Peak commanded speed about 0.10 m/s at --scale 1.0 (hard cap on --scale: 1.5).

THIS GOES BEYOND THE STAGED-TEST LIMITS (3 cm, 0.05 m/s, 600 N/m): stiffness 2000 N/m, up to about
19 cm from the start. Clear a box 13 cm deep x 25 cm wide x 15 cm tall in front of and above the
flange, and mind the elbow.

Safety:
  - never calls Enable() or ClearFault(); aborts unless no fault, operational, IDLE, tool Flange
  - SetMaxContactWrench [30,30,30,5,5,5]; RDK speed limit 0.15 m/s, acceleration 0.5 m/s^2
  - trips -> robot.Stop(): measured speed > 0.30 m/s, force change from baseline > 25 N, outside the envelope
  - soft stop: create the file server/hw/out/STOP (it ramps down, returns and stops within about 8 s)
  - the E-STOP is the only instant stop
Result: server/hw/out/demo.json and demo.csv.
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
from server.hw._common import attach_arm, connect_checked, flag, option, out_dir, sim_arm  # noqa: E402

K = 2000.0                 # N/m translational (rotation nominal)
TRIP_SPEED = 0.30          # m/s measured
TRIP_DFORCE = 25.0         # N from baseline
RAMP = 6.0                 # s ramp in / out
DT = 0.01
MAX_SCALE = 1.5
ENV = dict(inward=(-0.015, 0.135), lateral=(-0.125, 0.125), up=(-0.015, 0.145))   # m, relative to start


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def pattern(t: float, amp: float, scale: float):
    """(inward, lateral, up) in metres; amp ramps 0..1."""
    inward = amp * (0.07 + 0.04 * math.sin(2 * math.pi * scale * t / 5.0 - math.pi / 2))
    lateral = amp * 0.10 * math.sin(2 * math.pi * scale * t / 9.0)
    up = amp * (0.07 + 0.05 * math.sin(2 * math.pi * scale * t / 6.5 - math.pi / 2))
    return inward, lateral, up


def run(duration: float, scale: float, sim: bool) -> dict:
    scale = min(max(scale, 0.1), MAX_SCALE)
    limits = Limits(k_max=K, k_hold=K, max_lead_m=0.05, max_linear_vel=0.15, max_linear_acc=0.5,
                    trip_speed=TRIP_SPEED, trip_force=40.0, max_contact_n=30.0, max_contact_nm=5.0,
                    watchdog_s=0.2, box_half_m=(0.17, 0.16, 0.15))
    stop_file = out_dir() / "STOP"
    if stop_file.exists():
        stop_file.unlink()
    if sim:
        arm, robot, k_nom = sim_arm(limits), None, [10000.0] * 3 + [1500.0] * 3
    else:
        robot, rdk, k_nom = connect_checked(require_tool="Flange")
        arm = attach_arm(limits, robot, rdk, k_nom)

    rows, result = [], dict(duration_req=duration, scale=scale, sim=sim, tripped=None, stopped_by_file=False)
    tripped = [None]
    done = threading.Event()

    def hard_stop(reason):
        if tripped[0] is None:
            tripped[0] = reason
        try:
            arm.stop()
        except Exception as e:
            print("arm.stop() raised:", repr(e))

    def deadline():
        if not done.wait(duration + 40.0):
            print("HARD DEADLINE reached -> Stop()")
            hard_stop("hard deadline")
            os._exit(5)
    threading.Thread(target=deadline, daemon=True).start()

    try:
        acc, n = [0.0, 0.0, 0.0], 0
        t_end = time.monotonic() + 1.0
        while time.monotonic() < t_end:
            acc = [a + f for a, f in zip(acc, arm.get_state().force)]
            n += 1
            time.sleep(DT)
        base = [a / n for a in acc]
        p0 = arm.get_state().pos
        r = math.hypot(p0[0], p0[1])
        u_in = (-p0[0] / r, -p0[1] / r, 0.0)
        u_lat = (-u_in[1], u_in[0], 0.0)
        print(f"start {[round(v, 4) for v in p0]} baseline {[round(v, 2) for v in base]} N "
              f"inward {[round(v, 3) for v in u_in]}")
        result.update(start_pos=p0, baseline=base, u_in=u_in)
        arm.start_compliance()
        start = arm.start_pos
        t0 = time.monotonic()
        next_tick, t_stop_req, last_print = t0, None, 0.0
        while True:
            t = time.monotonic() - t0
            if t_stop_req is None and (t >= duration - RAMP or stop_file.exists()):
                t_stop_req = t
                result["stopped_by_file"] = stop_file.exists()
            amp = min(1.0, t / RAMP)
            if t_stop_req is not None:
                amp = min(amp, max(0.0, 1.0 - (t - t_stop_req) / RAMP))
                if t - t_stop_req > RAMP + 1.5:
                    break
            a, b, c = pattern(t, amp, scale)
            target = tuple(start[i] + a * u_in[i] + b * u_lat[i] + (c if i == 2 else 0.0) for i in range(3))
            st = arm.get_state()
            d = [p - s for p, s in zip(st.pos, start)]
            din = sum(d[i] * u_in[i] for i in range(3))
            dlat = sum(d[i] * u_lat[i] for i in range(3))
            dup = d[2]
            df = [f - b0 for f, b0 in zip(st.force, base)]
            speed = norm(st.vel)
            rows.append([round(t, 3), *st.pos, speed, norm(df), *target])
            reason = None
            if st.mode != "compliant":
                reason = f"arm left compliant mode: {st.mode} / {st.fault}"
            elif speed > TRIP_SPEED:
                reason = f"speed {speed:.3f} m/s > {TRIP_SPEED}"
            elif norm(df) > TRIP_DFORCE:
                reason = f"force change {norm(df):.1f} N > {TRIP_DFORCE}"
            elif not (ENV["inward"][0] <= din <= ENV["inward"][1]
                      and ENV["lateral"][0] <= dlat <= ENV["lateral"][1]
                      and ENV["up"][0] <= dup <= ENV["up"][1]):
                reason = f"outside envelope: inward {din * 100:.1f} lateral {dlat * 100:.1f} up {dup * 100:.1f} cm"
            if reason:
                print(f"TRIP at t={t:.1f}s:", reason)
                hard_stop(reason)
                break
            arm.set_target(target)
            if t - last_print > 30.0:
                last_print = t
                print(f"  t={t:5.0f}s speed {speed:.3f} m/s force change {norm(df):.1f} N "
                      f"pos(in,lat,up) {din * 100:.1f},{dlat * 100:.1f},{dup * 100:.1f} cm", flush=True)
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
            try:
                robot.SetCartesianImpedance(k_nom)
                result["k_nom_restored"] = True
                print("K_x_nom restored after trip")
            except Exception as e:
                result["k_nom_restored"] = False
                print("K_x_nom restore after trip refused:", repr(e)[:200])
        try:
            arm.close()   # hold -> SetCartesianImpedance(K_x_nom) -> Stop()
            if tripped[0] is None:
                result["k_nom_restored"] = True
        except Exception as e:
            print("arm.close() raised:", repr(e))
        done.set()

    tag = f"demo{'_sim' if sim else ''}"
    if rows:
        start = result["start_pos"]
        err = [math.dist(r[1:4], r[6:9]) for r in rows]
        result.update(samples=len(rows), duration=rows[-1][0], max_speed=max(r[4] for r in rows),
                      max_dforce=max(r[5] for r in rows), max_track_err_mm=max(err) * 1000,
                      mean_track_err_mm=sum(err) / len(err) * 1000,
                      end_mm=math.dist(rows[-1][1:4], start) * 1000,
                      max_dist_mm=max(math.dist(r[1:4], start) for r in rows) * 1000)
        print(f"DEMO: {result['duration']:.1f} s, {len(rows)} samples; max speed {result['max_speed']:.3f} m/s; "
              f"max force change {result['max_dforce']:.1f} N; tracking error max "
              f"{result['max_track_err_mm']:.1f} mm mean {result['mean_track_err_mm']:.1f} mm; furthest "
              f"{result['max_dist_mm']:.0f} mm from start; ended {result['end_mm']:.1f} mm from start; "
              f"tripped: {result['tripped']}")
        with open(out_dir() / f"{tag}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow("t px py pz speed dforce tx ty tz".split())
            w.writerows(rows[::5])
    (out_dir() / f"{tag}.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    if robot is not None:
        time.sleep(0.5)
        print(f"after: fault={robot.fault()} mode={robot.mode()} operational={robot.operational()}")
    return result


def main() -> int:
    result = run(float(option("--seconds", "240")), float(option("--scale", "1.0")), flag("--sim"))
    return 0 if result.get("tripped") is None else 6


if __name__ == "__main__":
    sys.exit(main())
