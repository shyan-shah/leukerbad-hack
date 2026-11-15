"""Tuning measurements on the arm (package K3). MOVES THE ARM. A person touches the handle.

    python robot/tune.py                 real arm (same start-up checks as safety_check.py)
    python robot/tune.py --only 1,2      single measurements
    python robot/tune.py --sim           dry run on SimArm (numbers mean nothing, it only tests the script)

Run it only after robot/safety_check.py has passed with the technician. Each step waits for
Enter; while it waits the arm is in soft hold. It measures, it does not judge: the numbers go
into robot/TUNING.md section 5.

  1  stiffness-call latency (50 calls)
  2  empty-handle force along the reach line
  3  drag on a free reach axis
  4  wall feel at 300 / 500 / 600 N/m     (800 is above k_max and is not tested)
  5  relaxed arm resting on the handle
  6  assist feel at 200 / 400 / 600 N/m
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from robot import safety_check as sc  # noqa: E402
from robot.safety_check import F_PRESENT, OCCUPIED_WINDOW_S, Rig, Sample, norm, sub  # noqa: E402

MEASUREMENTS: list[tuple[int, str, object]] = []


def measure(num: int, title: str):
    def deco(fn):
        MEASUREMENTS.append((num, title, fn))
        return fn
    return deco


def _note(rig: Rig, question: str) -> str:
    return "" if rig.sim else rig.ask(f"  {question} (free text, Enter to skip): ").strip()


def _baseline(rig: Rig) -> None:
    rig.pause("BASELINE. NOBODY touches the arm or the handle. Reads the empty force for 1 s; no motion.")
    acc = [0.0, 0.0, 0.0]
    for _ in range(100):
        acc = [a + v for a, v in zip(acc, rig.state().force)]
        rig.tick()
    rig.baseline = tuple(a / 100 for a in acc)
    rig.say(f"  empty force at the start: {[round(v, 2) for v in rig.baseline]} N (|F| {norm(rig.baseline):.2f})")


@measure(1, "Stiffness-call latency")
def m1(rig: Rig) -> dict:
    rig.wait("MEASUREMENT 1. HANDS OFF. 50 stiffness calls (300 and 310 N/m) while holding; no motion. (10 s)")
    if not hasattr(rig.arm, "_set_impedance"):
        return dict(summary=f"N/A in sim (SimArm applies stiffness after {rig.arm.stiffness_latency_s * 1000:.0f} ms)")
    ms = []
    for i in range(50):
        rig.run(0.1, lambda s: rig.start)
        t0 = time.perf_counter()
        with rig.arm._lock:
            rig.arm._set_impedance((300.0 + 10.0 * (i % 2),) * 3)
        ms.append((time.perf_counter() - t0) * 1000.0)
        rig.arm.set_target(rig.start)
    mode = rig.state().mode
    rig.settle((rig.lim.k_hold,) * 3, 0.3)
    return dict(median_ms=statistics.median(ms), max_ms=max(ms), mode_after=mode,
                summary=f"median {statistics.median(ms):.0f} ms, max {max(ms):.0f} ms over 50 calls"
                        + ("" if mode == "compliant" else f"; ARM LEFT COMPLIANT MODE ({mode}): a call outlasted the watchdog"))


@measure(2, "Empty-handle force along the reach line")
def m2(rig: Rig) -> dict:
    stops = [0.0, 0.10, 0.20, 0.28]
    rig.wait("MEASUREMENT 2. HANDS OFF. The arm moves the empty handle along the reach line by itself at "
             "5 cm/s to 28 cm, pausing at 0, 10, 20 and 28 cm, then returns. (25 s)")
    rig.settle((rig.lim.k_max,) * 3)
    readings = []
    pos_s = 0.0
    for stop in stops:
        s0, T = pos_s, abs(stop - pos_s) / 0.05
        out = rig.run(T + 2.0, lambda s: rig.on_path(s0 + (stop - s0) * (min(1.0, s.t / T) if T > 0 else 1.0)))
        pos_s = stop
        if out[-1].mode != "compliant":
            return dict(summary=f"tripped at {stop * 100:.0f} cm: {out[-1].fault}", readings=readings)
        tail = [s for s in out if s.t > out[-1].t - 1.0]
        f = tuple(sum(s.force[i] for s in tail) / len(tail) for i in range(3))
        readings.append(dict(at_cm=stop * 100, hand_cm=rig.along(tail[-1].pos) * 100, force=f,
                             change_n=norm(sub(f, rig.baseline))))
    rig.recenter()
    worst = max(r["change_n"] for r in readings)
    return dict(readings=readings, max_change_n=worst,
                summary="change from the start-pose reading: "
                        + ", ".join(f"{r['at_cm']:.0f} cm {r['change_n']:.2f} N" for r in readings)
                        + f"; largest {worst:.2f} N (F_PRESENT is {F_PRESENT} N)")


@measure(3, "Drag on a free reach axis")
def m3(rig: Rig) -> dict:
    rig.wait("MEASUREMENT 3. Reach axis free (0 N/m), walls on. Slide the handle back and forth along the reach, "
             "about 15 cm each way: a few slow strokes (about 10 cm/s), then a few faster (about 20 cm/s). (25 s)")
    rig.settle(rig.k_axes(0.0, rig.k_wall))

    def sim(s: Sample):
        f = 2.0 if int(s.t / 1.5) % 2 == 0 else -2.0
        return (tuple(f * c for c in rig.u), 0.0)

    out = rig.run(25.0, lambda s: rig.on_path(min(max(rig.along(s.pos), 0.0), rig.reach_m)),
                  live=rig.live_line, sim_script=sim)
    bins = {"0.05-0.15 m/s": (0.05, 0.15), "0.15-0.25 m/s": (0.15, 0.25)}
    res = {}
    for name, (lo, hi) in bins.items():
        f = [abs(s.force[rig.axis] - rig.baseline[rig.axis]) for s in out if lo <= abs(s.vel[rig.axis]) < hi]
        res[name] = dict(n=len(f), mean_n=(sum(f) / len(f)) if f else None)
    trip = sc._tripped(out)
    rig.recover()
    return dict(bins=res, tripped=trip, feel=_note(rig, "How does the free axis feel?"),
                summary="; ".join(f"{k}: " + (f"{v['mean_n']:.1f} N mean over {v['n']} samples" if v["n"] else "no samples")
                                  for k, v in res.items()) + (f"; tripped: {trip}" if trip else ""))


@measure(4, "Wall feel at 300 / 500 / 600 N/m")
def m4(rig: Rig) -> dict:
    rows = []
    e = tuple(1.0 if i == rig.side else 0.0 for i in range(3))
    for k in (300.0, 500.0, 600.0):
        rig.wait(f"MEASUREMENT 4, wall {k:.0f} N/m. Push the handle sideways about 2 cm, slowly, then let go. (8 s)")
        rig.settle(rig.k_axes(rig.lim.k_hold, k))
        out = rig.run(8.0, lambda s: rig.start, live=rig.live_line,
                      sim_script=lambda s: (tuple(0.02 * k * c for c in e), 0.0) if s.t < 2.5 else None)
        i = max(range(len(out)), key=lambda j: abs(out[j].pos[rig.side] - rig.start[rig.side]))
        d = abs(out[i].pos[rig.side] - rig.start[rig.side])
        f = abs(out[i].force[rig.side] - rig.baseline[rig.side])
        tail = [abs(s.pos[rig.side] - rig.start[rig.side]) for s in out if s.t > out[-1].t - 0.5]
        rows.append(dict(k=k, pushed_mm=d * 1000, force_n=f, measured_n_per_m=(f / d) if d > 1e-4 else None,
                         return_mm=sum(tail) / len(tail) * 1000, tripped=sc._tripped(out),
                         feel=_note(rig, f"How does the {k:.0f} N/m wall feel (soft, firm, buzzing)?")))
    return dict(rows=rows, summary="; ".join(
        f"{r['k']:.0f}: {r['measured_n_per_m'] or 0:.0f} N/m measured, back to {r['return_mm']:.1f} mm"
        + (f" ({r['feel']})" if r["feel"] else "") for r in rows))


@measure(5, "Relaxed arm resting on the handle")
def m5(rig: Rig) -> dict:
    rig.wait("MEASUREMENT 5. Soft hold. Rest a RELAXED hand and forearm on the handle and keep still. (6 s)")
    out = rig.run(6.0, lambda s: rig.start, live=rig.live_line,
                  sim_script=lambda s: ((0.0, 0.0, -8.0), 0.0))
    f = [rig.rel(s.force) for s in out if s.t > 1.0]
    low = sorted(f)[len(f) // 20] if f else 0.0
    return dict(mean_n=sum(f) / len(f), p5_n=low,
                summary=f"relaxed arm: mean {sum(f) / len(f):.1f} N, lowest 5% {low:.1f} N above the empty baseline "
                        f"(F_PRESENT is {F_PRESENT} N; compare with measurement 2)")


@measure(6, "Assist feel at 200 / 400 / 600 N/m")
def m6(rig: Rig) -> dict:
    lead, rows = rig.lim.max_lead_m, []
    limp = tuple(2.0 * c for c in rig.u[:2]) + (-8.0,)
    for k in (200.0, 400.0, 600.0):
        rig.wait(f"MEASUREMENT 6, assist {k:.0f} N/m. Hold the handle with a RELAXED arm; the arm carries your "
                 f"hand 25 cm along the reach. Keep holding until it stops. (up to 20 s)")
        rig.settle(rig.k_axes(k, rig.k_wall))
        occ = {"t": None}

        def target(s: Sample):
            if rig.rel(s.force) > F_PRESENT:
                occ["t"] = s.t
            held = occ["t"] is not None and s.t - occ["t"] <= OCCUPIED_WINDOW_S
            p = rig.along(s.pos)
            return rig.on_path(min(p + lead, 0.25) if held else p)       # same hands-off rule as check 10

        out = rig.run(20.0, target, live=rig.live_line, sim_script=lambda s: (limp, 150.0),
                      until=lambda s, o: rig.along(s.pos) >= 0.24)
        moving = [s for s in out if 0.03 <= rig.along(s.pos) <= 0.22]
        v = [abs(s.vel[rig.axis]) for s in moving]
        rows.append(dict(k=k, reached_cm=max(rig.along(s.pos) for s in out) * 100, seconds=out[-1].t,
                         mean_speed=(sum(v) / len(v)) if v else None, peak_speed=max(v) if v else None,
                         mean_force_n=(sum(rig.rel(s.force) for s in moving) / len(moving)) if moving else None,
                         tripped=sc._tripped(out),
                         feel=_note(rig, f"How does {k:.0f} N/m assist feel (weak, right, pushy, vibration)?")))
        rig.recover()
    return dict(rows=rows, summary="; ".join(
        f"{r['k']:.0f}: reached {r['reached_cm']:.0f} cm in {r['seconds']:.1f} s, mean "
        f"{(r['mean_speed'] or 0):.2f} m/s, {(r['mean_force_n'] or 0):.1f} N on the handle"
        + (f", tripped {r['tripped']}" if r["tripped"] else "") + (f" ({r['feel']})" if r["feel"] else "")
        for r in rows))


def run_measurements(rig: Rig, only: set[int] | None = None) -> list[dict]:
    results = []
    try:
        _baseline(rig)
        for num, title, fn in MEASUREMENTS:
            if only is not None and num not in only:
                continue
            try:
                res = fn(rig)
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                try:
                    rig.arm.hold()
                except Exception:  # noqa: BLE001
                    pass
                res = dict(summary=f"measurement crashed: {exc!r}")
            results.append(dict(num=num, title=title, **res))
            rig.say(f"  ==> {num}. {title}: {res['summary']}\n")
    except KeyboardInterrupt:
        rig.say("\n  Ctrl+C: holding, then closing.")
        try:
            rig.arm.hold()
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            rig.arm.close()
        except Exception as exc:  # noqa: BLE001
            rig.say(f"  arm.close() raised {exc!r}: run python robot/recover.py")
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tuning measurements for the rehab arm (K3).")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--serial")
    ap.add_argument("--tool", default="RehabHandle")
    ap.add_argument("--reach-axis", choices=["x", "y"])
    ap.add_argument("--reach-sign", type=int, choices=[1, -1])
    ap.add_argument("--only", help="comma-separated measurement numbers, e.g. 1,2")
    ap.add_argument("--k-wall", type=float, default=sc.K_WALL)
    ap.add_argument("--k-assist", type=float, default=sc.K_ASSIST)
    ap.add_argument("--k-resist", type=float, default=sc.K_RESIST)
    ap.add_argument("--reach-m", type=float, default=sc.REACH_M)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    only = {int(v) for v in args.only.split(",")} if args.only else None

    rig = sc.build_sim(args) if args.sim else sc.build_real(args)
    if not args.sim:
        print("\nOnly after safety_check.py has passed. E-stop holder in place, technician present, workspace clear.")
        if input("Type go to start: ").strip().lower() != "go":
            rig.arm.close()
            print("not started")
            return 1
    results = run_measurements(rig, only)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_dir = Path(args.out) if args.out else Path(__file__).with_name("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"tune_{stamp}_{'sim' if args.sim else 'arm'}.json"
    out.write_text(json.dumps(dict(when=stamp, sim=args.sim, baseline=rig.baseline, results=results),
                              indent=2, default=str), encoding="utf-8")
    print("\n| # | Measurement | Result |\n|---|---|---|")
    for r in results:
        print(f"| {r['num']} | {r['title']} | {r['summary']} |")
    print(f"\nsaved {out}{'  [SIMULATED: numbers mean nothing]' if args.sim else ''}\nCopy the table into robot/TUNING.md section 5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
