"""Starting dial from a short transparent assessment (package S5).

TEAM HEURISTIC, NOT A CLINICAL ASSESSMENT. It only picks where the auto dial starts; the
auto dial (software/adapt.py) then adjusts it rep by rep. It makes no claim about the
patient's impairment and must not be presented as a measure of it.

Procedure: the patient does about 3 reps with the dial at 0 (transparent: the reach axis
floats and the tunnel walls stay). From the last 3 transparent reps:

- ``completed_share``: share of reps that reached 90% of the reach,
- ``rom_share``: mean range of motion divided by 90% of the reach length, capped at 1,
- ``contribution``: mean contribution (team-defined index, 0..1).

Rule:
1. If no rep was completed, start at full assistance, ``+1.0``.
2. Otherwise ``ability = (completed_share + rom_share + contribution) / 3`` (0..1) and
   ``dial = 1.0 - 1.6 * ability``, clamped to [``START_MIN``, ``START_MAX``] = [-0.3, +1.0]
   and rounded to the nearest 0.05. So ability 0 gives +1.0, about 0.63 gives 0 and
   anything above about 0.81 gives -0.3. A session never starts beyond -0.3 resistance;
   auto mode lowers it further only if reps succeed.

The constants are team choices for the demo, not validated thresholds.
"""

from __future__ import annotations

from server.contract import RepResult

__all__ = ["starting_dial", "assessment", "HEURISTIC_LABEL", "N_REPS",
           "START_MIN", "START_MAX", "SLOPE", "STEP"]

HEURISTIC_LABEL = "team heuristic, not a clinical assessment"
N_REPS = 3                 # transparent reps used (the last N_REPS given)
OUT_DONE = 0.9             # completion threshold used by the engine (share of reach)
START_MAX = 1.0            # full assistance
START_MIN = -0.3           # mildest resistance a session may start at
SLOPE = 1.6                # dial = 1 - SLOPE * ability
STEP = 0.05                # rounding of the starting dial


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def assessment(reps: list[RepResult], reach_m: float = 0.30) -> dict:
    """Components and result of the rule, for display.

    Returns ``{"n_reps", "completed_share", "rom_share", "contribution", "ability",
    "dial", "label"}``. Raises ValueError if there is no transparent rep or reach_m <= 0.
    """
    if not reach_m > 0:
        raise ValueError(f"reach_m must be > 0, got {reach_m}")
    used = [r for r in reps if r.mode == "transparent"][-N_REPS:]
    if not used:
        raise ValueError("need at least one transparent rep (mode 'transparent', dial 0)")
    n = len(used)
    completed_share = sum(1 for r in used if r.completed) / n
    rom_share = _clip01(sum(r.rom_m for r in used) / n / (OUT_DONE * reach_m))
    contrib = _clip01(sum(r.contribution for r in used) / n)
    ability = (completed_share + rom_share + contrib) / 3.0
    if completed_share == 0:
        dial = START_MAX
    else:
        raw = min(START_MAX, max(START_MIN, 1.0 - SLOPE * ability))
        dial = round(round(raw / STEP) * STEP, 6)
        dial = 0.0 if dial == 0 else dial
    return {"n_reps": n, "completed_share": completed_share, "rom_share": rom_share,
            "contribution": contrib, "ability": ability, "dial": float(dial),
            "label": HEURISTIC_LABEL}


def starting_dial(reps: list[RepResult], reach_m: float = 0.30) -> float:
    """Starting dial from transparent assessment reps. Team heuristic, not a clinical assessment."""
    return assessment(reps, reach_m)["dial"]
