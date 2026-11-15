"""Two weeks of SIMULATED rehab history for one fictional patient.

This is an illustration we wrote to show what the physio dashboard and deck
would look like over time. It is NOT clinical data, NOT from a real person and
NOT from the robot. Every row is stored with simulated=True and the patient's
display name contains "(SIMULATED)".

The trend (assistance falling, contribution and force rising, smoother and
straighter movement, one bad day) is a plausible shape we chose, not a result.

TODO(S0d): once software/sim_patient.py is on main, consider generating the
per-rep numbers by running the simulated patient instead of sampling them here.

Run:  python -m server.simulate            (adds history to server/data/rehab.db)
      python -m server.simulate --fresh    (deletes the database first)
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from . import db
from .contract import RepResult, SessionSummary
from .stats import mode_of

START = datetime(2026, 10, 31, 9, 30)   # fixed so the same seed gives identical data


def _lerp(a: float, b: float, x: float) -> float:
    return a + (b - a) * x


def make_history(conn, patient_id: str = "sim-anna", display_name: str = "Anna (SIMULATED)",
                 days: int = 14, sessions_per_day: int = 1, reps_per_session: int = 30,
                 seed: int = 7) -> None:
    if "SIMULATED" not in display_name.upper():
        display_name = f"{display_name} (SIMULATED)"
    rng = np.random.default_rng(seed)
    db.upsert_patient(conn, patient_id, display_name, simulated=True)
    bad_day = min(8, days - 1) if days > 3 else -1

    for day in range(days):
        for k in range(sessions_per_day):
            x = day / max(days - 1, 1)                       # 0 on day 1 .. 1 on the last day
            bad = 0.35 if day == bad_day else 0.0             # one bad day
            xe = max(0.0, x - bad)                            # effective progress that day
            sid = f"{patient_id}-d{day + 1:02d}-s{k + 1}"
            started = START + timedelta(days=day, hours=5 * k)
            # dial falls smoothly through each session, and each day starts about where the last ended
            dial_a = float(np.clip(_lerp(0.95, -0.10, xe) + rng.normal(0, 0.03), -0.6, 1.0))
            dial_b = float(np.clip(dial_a - 0.12 - 0.08 * xe + rng.normal(0, 0.03), -0.6, 1.0))
            reps: list[RepResult] = []
            t = 2.0
            for i in range(reps_per_session):
                dial = float(np.clip(_lerp(dial_a, dial_b, i / max(reps_per_session - 1, 1)) + rng.normal(0, 0.02), -0.6, 1.0))
                fatigue = 0.15 * i / reps_per_session         # a little worse late in the session
                cap = float(np.clip(_lerp(0.28, 0.92, xe) - fatigue + rng.normal(0, 0.06), 0.02, 1.0))
                contribution = float(np.clip(cap + rng.normal(0, 0.04), 0.0, 1.0))
                duration = float(max(2.5, _lerp(7.5, 4.2, cap) + rng.normal(0, 0.4)))
                err = float(max(0.003, _lerp(0.035, 0.010, cap) + rng.normal(0, 0.003)))
                completed = bool(rng.random() < min(0.99, _lerp(0.6, 0.99, cap) + 0.3 * max(dial, 0.0)))
                rescued = bool(dial > 0.05 and rng.random() < 0.35 * (1 - cap))
                rom = float(np.clip(_lerp(0.17, 0.29, cap) + rng.normal(0, 0.01), 0.05, 0.30))
                if not completed:
                    rom = min(rom, 0.25)
                # force the person applies: small when assisted, up to the 15 N resistance band (MASTER_PLAN 4.2) when resisted
                peak = float(max(1.0, _lerp(3.0, 10.0, cap) + 15.0 * max(-dial, 0.0) + rng.normal(0, 0.8)))
                reps.append(RepResult(
                    session_id=sid, idx=i, mode=mode_of(dial), dial=round(dial, 3), t_start=round(t, 2),
                    duration_s=round(duration, 2), rom_m=round(rom, 4), path_err_mean_m=round(err, 4),
                    path_err_max_m=round(err * float(rng.uniform(1.8, 2.6)), 4),
                    sparc=round(float(_lerp(-2.4, -1.55, cap) + rng.normal(0, 0.06)), 3),
                    peak_force_n=round(peak, 2), mean_force_n=round(peak * float(rng.uniform(0.4, 0.5)), 2),
                    contribution=round(contribution, 3), completed=completed, simulated=True, rescued=rescued))
                t += duration * 2 + 1.0
            ended = started + timedelta(seconds=t)
            db.save_session(conn, SessionSummary(
                session_id=sid, patient_id=patient_id, started_at=started.isoformat(timespec="seconds"),
                ended_at=ended.isoformat(timespec="seconds"), exercise="reach",
                n_reps=len(reps), simulated=True))
            for r in reps:
                db.save_rep(conn, r, commit=False)
            conn.commit()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Write SIMULATED rehab history into the database.")
    ap.add_argument("--db", default=db.DEFAULT_PATH)
    ap.add_argument("--fresh", action="store_true", help="delete the database file first")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    if a.fresh and Path(a.db).exists():
        Path(a.db).unlink()
    conn = db.connect(a.db)
    make_history(conn, days=a.days, seed=a.seed)
    n = sum(s.n_reps for s in db.list_sessions(conn, "sim-anna"))
    print(f"SIMULATED history written to {a.db}: {len(db.list_sessions(conn, 'sim-anna'))} sessions, {n} reps")
    conn.close()


if __name__ == "__main__":
    main()
