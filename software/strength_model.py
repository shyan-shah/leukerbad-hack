"""Team heuristic that learns from the patient's own sessions. Not a clinical assessment and not trained on patient data.

Pure functions. The resistance for a resisted set is a fraction of the force the patient
pushed comfortably in the calibration push. The fraction starts at ``START_FRACTION``, stays
within ``MIN_FRACTION`` to ``MAX_FRACTION`` and moves ``STEP`` after each set: up when the set
was easy (every rep completed, on time, no stall rescue), down when it was hard. All numbers
are team-chosen starting values.
"""
from __future__ import annotations

__all__ = ["new_state", "resistance_for", "update", "MIN_RESISTANCE_N"]

START_FRACTION = 0.5
MIN_FRACTION = 0.3
MAX_FRACTION = 0.8
STEP = 0.05
MIN_RESISTANCE_N = 3.0       # N, the lightest resistance ever set
ON_TIME_S = 6.0              # s, an out phase longer than this is not "on time"


def new_state() -> dict:
    return {"v": 1, "fraction": START_FRACTION, "sets": 0}


def _fraction(state: dict | None) -> float:
    f = float((state or {}).get("fraction", START_FRACTION))
    return min(MAX_FRACTION, max(MIN_FRACTION, f))


def resistance_for(comfort_force_n: float, state: dict | None, max_resistance_n: float) -> dict:
    """Resistance (N) for a set: fraction * comfort force, clamped to MIN_RESISTANCE_N ..
    max_resistance_n. ``dial`` is the engine dial that gives it (-resistance / max, in [-1, 0))."""
    if not max_resistance_n > 0:
        raise ValueError(f"max_resistance_n must be > 0, got {max_resistance_n}")
    frac = _fraction(state)
    lo = min(MIN_RESISTANCE_N, float(max_resistance_n))
    r = min(float(max_resistance_n), max(lo, frac * max(0.0, float(comfort_force_n))))
    return {"resistance_n": r, "dial": -r / float(max_resistance_n), "fraction": frac}


def update(state: dict | None, reps) -> dict:
    """New state after a set. ``reps``: RepResults (or dicts with completed, rescued,
    duration_s). Easy = all completed, none rescued, none slower than ON_TIME_S: fraction up
    one STEP. Anything else: down one STEP. No reps: unchanged."""
    out = dict(new_state() | dict(state or {}))
    out["fraction"] = _fraction(out)
    reps = list(reps or [])
    if not reps:
        return out

    def g(r, name, default):
        return r.get(name, default) if isinstance(r, dict) else getattr(r, name, default)

    easy = all(bool(g(r, "completed", False)) and not bool(g(r, "rescued", False))
               and float(g(r, "duration_s", 0.0)) <= ON_TIME_S for r in reps)
    f = out["fraction"] + (STEP if easy else -STEP)
    out["fraction"] = round(min(MAX_FRACTION, max(MIN_FRACTION, f)), 4)
    out["sets"] = int(out.get("sets", 0)) + 1
    return out
