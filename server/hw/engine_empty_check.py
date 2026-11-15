"""Empty-handle run of each exercise through the real engine. COMMANDS THE ARM (soft hold; it must not move).

    python -u -m server.hw.engine_empty_check                 # dry run: prints the plan
    python -u -m server.hw.engine_empty_check --go            # every LIVE exercise, 20 s each
    python -u -m server.hw.engine_empty_check --go reach push # only these

NOBODY touches the arm. For each exercise: ZeroFTSensor at the start pose, software.engine.Engine on
the real arm (robot/arm.py limits, contact wrench [30, 30, 30, 5, 5, 5]) for --seconds (default 20),
then stop. Pass per exercise: no rep, try or circle started, phase never "out"/"back", the hand
stayed within 1 cm of where it began along the reach and 3 cm in total, the arm never left
"compliant" (no trip), no engine error.

Guard on top of the arm's own trips: if the empty hand moves more than 3 cm, the engine is stopped
at once (hold) and the run ends. Connects through CheckedArm (never Enable()/ClearFault(); needs
fault-free, operational, IDLE, tool Flange, hand within 2 cm of the configured start pose).
Always ends with Arm.close() (nominal stiffness restored, Stop()).
Result: server/hw/out/engine_empty_check.json.
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np

from server.hw._common import CONFIG, flag, option, out_dir, positional
from server.hw.checked_arm import CheckedArm
from server.hw.home_check import countdown

GUARD_M = 0.03


def run_one(arm, exercise: str, seconds: float, reach_sign: int) -> dict:
    from software.engine import Engine

    samples = []
    arm.zero_force()
    time.sleep(0.5)
    f0 = np.array(arm.get_state().force)
    eng = Engine(arm=arm, session_id=f"empty-{exercise}", patient_id="nobody", simulated=False,
                 reach_axis=arm.reach_axis, reach_sign=reach_sign, exercise=exercise,
                 on_sample=samples.append)
    eng.start()
    p0 = np.array(arm.get_state().pos)
    t0, guard = time.time(), None
    try:
        while time.time() - t0 < seconds:
            time.sleep(0.05)
            st = arm.get_state()
            moved = float(np.linalg.norm(np.array(st.pos) - p0))
            if moved > GUARD_M:
                guard = f"empty hand moved {moved * 100:.1f} cm"
                break
            if st.mode != "compliant" or eng.error is not None:
                break
    finally:
        eng.stop()
    st = arm.get_state()
    P = np.array([s.pos for s in samples]) if samples else np.array([p0])
    F = np.array([s.force for s in samples]) if samples else np.zeros((1, 3))
    V = np.array([s.vel for s in samples]) if samples else np.zeros((1, 3))
    phases = sorted({s.phase for s in samples})
    r = dict(exercise=exercise, seconds=round(time.time() - t0, 1), samples=len(samples),
             rate_hz=round(len(samples) / max(time.time() - t0, 1e-6)),
             zero_force_n=round(float(np.linalg.norm(f0)), 2), baseline_n=round(float(np.linalg.norm(eng.force_baseline)), 2),
             reps=eng.rep_count, phases=phases, engine_phase=eng.phase,
             moved_along_mm=round(float(np.abs(P[:, arm.reach_axis] - p0[arm.reach_axis]).max()) * 1000, 2),
             moved_total_mm=round(float(np.linalg.norm(P - p0, axis=1).max()) * 1000, 2),
             end_mm=round(float(np.linalg.norm(np.array(st.pos) - p0)) * 1000, 2),
             max_speed=round(float(np.linalg.norm(V, axis=1).max()), 4),
             max_force_n=round(float(np.linalg.norm(F, axis=1).max()), 2),
             arm_mode=st.mode, fault=st.fault, guard=guard,
             engine_error=repr(eng.error) if eng.error else None)
    r["pass"] = (r["reps"] == 0 and not ({"out", "back"} & set(phases)) and r["moved_along_mm"] < 10.0
                 and r["moved_total_mm"] < 30.0 and guard is None and st.fault is None
                 and r["engine_error"] is None)
    print(f"  {exercise:>8}: {'PASS' if r['pass'] else 'FAIL'}  reps {r['reps']}  phases {phases}  moved along "
          f"{r['moved_along_mm']} mm, total {r['moved_total_mm']} mm  max speed {r['max_speed']} m/s  max |F| "
          f"{r['max_force_n']} N  {r['rate_hz']} Hz  mode {st.mode} fault {st.fault} guard {guard} error {r['engine_error']}")
    return r


def main() -> int:
    from software.exercises import LIVE

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    reach_sign = -1 if float(cfg.get("reach_sign", 1)) < 0 else 1
    seconds = float(option("--seconds", "20"))
    todo = [a for a in positional() if a in LIVE] or list(LIVE)
    if not flag("--go"):
        print(f"DRY RUN: would run {todo} for {seconds:.0f} s each on the real arm with an empty handle "
              f"(reach axis {'xyz'[int(cfg['reach_axis'])]}, sign {reach_sign:+d}).")
        return 0
    arm = CheckedArm.from_config()
    arm.connect()
    goal = np.array(cfg["start_pose"]["tcp_pose"][:3])
    d = float(np.linalg.norm(np.array(arm.get_state().pos) - goal))
    if d > 0.02:
        arm.close()
        print(f"ABORT: the hand is {d * 100:.1f} cm from the configured start pose (limit 2 cm). Home first.")
        return 3
    countdown([f"Empty-handle engine check: {', '.join(todo)}, {seconds:.0f} s each, soft hold at 300 N/m (pull: free "
               "along the reach in its setup phase).",
               "The arm must stay where it is. Nobody touches it. A 3 cm movement stops the run."])
    results, reason = [], None
    try:
        for ex in todo:
            r = run_one(arm, ex, seconds, reach_sign)
            results.append(r)
            if not r["pass"]:
                reason = f"{ex} failed"
                break
    except KeyboardInterrupt:
        reason = "Ctrl+C"
    except Exception as e:
        reason = f"error: {e!r}"
    finally:
        arm.close()
    print(f"STOPPED: {reason}" if reason else "completed: every exercise passed")
    (out_dir() / "engine_empty_check.json").write_text(json.dumps(dict(results=results, stopped=reason), indent=2),
                                                        encoding="utf-8")
    return 0 if reason is None else 6


if __name__ == "__main__":
    sys.exit(main())
