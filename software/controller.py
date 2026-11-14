"""Per-tick impedance command from the dial (package S2).

Pure function, no arm, no threads. See context/MASTER_PLAN.md sections 4.2 and 4.4.

The arm is a spring between the hand and the target, per base axis:
``force = K * (target - hand)``. Each tick the engine calls ``command`` and gets
one target point and one stiffness per base axis.

- The reach axis is the base axis the path lies along. The two other axes get
  ``K_WALL`` (the tunnel walls) and the target always sits on the path line, so
  a hand off the line is pushed back to it.
- ``D > 0`` assist: ``K_axis = D * K_ASSIST``. A min-jerk reference runs over the
  phase. Hand ahead of the reference: target on the hand (no along-path force).
  Hand behind: target leads the hand toward the reference by at most ``MAX_LEAD``.
- ``D = 0`` transparent: ``K_axis = 0``, target on the hand, walls stay.
- ``D < 0`` resist: ``K_axis = -D * K_RESIST``, target ``MAX_LEAD`` behind the hand
  toward the path start (in both phases), never beyond the start.
- ``rescued`` (stall rescue, decided by the engine): on the assist side the dial is
  raised to at least ``RESCUE_DIAL``; on the transparent or resist side it drops
  to transparent.
- The target never leaves the path segment.

Constants hold the section 4.2 start values. When Kian records final values in
robot/TUNING.md, edit only these constants.
"""

from __future__ import annotations

import numpy as np

from software.paths import LinePath, min_jerk

__all__ = [
    "K_WALL",
    "K_ASSIST",
    "K_RESIST",
    "MAX_LEAD",
    "REACH_M",
    "T_OUT_S",
    "T_BACK_S",
    "RESCUE_DIAL",
    "reach_axis_index",
    "reference_progress",
    "command",
]

# --- Tunable constants (section 4.2 start values) ---------------------------
K_WALL = 500.0       # N/m, across-path stiffness on the two non-reach axes
K_ASSIST = 400.0     # N/m at D = +1, max assist pull = 400 * 0.05 = 20 N
K_RESIST = 300.0     # N/m at D = -1, max resistance = 300 * 0.05 = 15 N
MAX_LEAD = 0.05      # m, furthest the target may sit from the hand along the path
REACH_M = 0.30       # m, reach length (used by the engine to build the path)
T_OUT_S = 4.0        # s, min-jerk reference time for the out phase
T_BACK_S = 4.0       # s, min-jerk reference time for the back phase
RESCUE_DIAL = 0.6    # stall rescue raises the dial to at least this on the assist side

_ALIGN_TOL = 1e-6    # path axis must lie along one base axis to within this


def reach_axis_index(path: LinePath) -> int:
    """Index (0, 1 or 2) of the base axis the path lies along.

    Raises ValueError if the path is not along a single base axis, because
    per-axis stiffness cannot make a tunnel around a diagonal line.
    """
    a = path.axis()
    i = int(np.argmax(np.abs(a)))
    if abs(abs(a[i]) - 1.0) > _ALIGN_TOL:
        raise ValueError(f"path must lie along one base axis, axis is {a}")
    return i


def reference_progress(phase: str, t_in_phase: float) -> float:
    """Min-jerk reference progress at ``t_in_phase``: 0 -> 1 on "out", 1 -> 0 on "back"."""
    if phase == "out":
        return min_jerk(0.0, 1.0, T_OUT_S, t_in_phase)
    if phase == "back":
        return min_jerk(1.0, 0.0, T_BACK_S, t_in_phase)
    raise ValueError(f'phase must be "out" or "back", got {phase!r}')


def command(dial: float, phase: str, s_hand: float, t_in_phase: float, pos, path: LinePath,
            rescued: bool) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return ``(target_pos, (kx, ky, kz))`` for one tick.

    ``dial`` in [-1, 1] (clamped), ``phase`` "out" or "back", ``s_hand`` the hand's
    progress along ``path`` (0 at start, 1 at end), ``t_in_phase`` seconds since
    the phase began, ``pos`` the hand position (m, base frame).
    """
    ref = reference_progress(phase, t_in_phase)  # validates phase
    pos = np.asarray(pos, dtype=float)
    if pos.shape != (3,) or not np.all(np.isfinite(pos)):
        raise ValueError(f"pos must be a finite (3,) point, got {pos}")
    if not np.isfinite(dial) or not np.isfinite(s_hand):
        raise ValueError(f"dial and s_hand must be finite, got {dial}, {s_hand}")

    axis_i = reach_axis_index(path)
    length = path.length()
    s = float(np.clip(s_hand, 0.0, 1.0))
    d = float(np.clip(dial, -1.0, 1.0))

    if rescued:
        d = max(d, RESCUE_DIAL) if d > 0 else 0.0

    if d > 0:
        k_axis = d * K_ASSIST
        direction = 1.0 if phase == "out" else -1.0
        behind_m = (ref - s) * direction * length  # > 0 when the hand lags the reference
        lead_m = min(max(behind_m, 0.0), MAX_LEAD)
        s_target = s + direction * lead_m / length
    elif d < 0:
        k_axis = -d * K_RESIST
        s_target = s - MAX_LEAD / length  # toward the start, clamped by point_at
    else:
        k_axis = 0.0
        s_target = s

    target = path.point_at(s_target)  # clamps to the segment
    k = [K_WALL, K_WALL, K_WALL]
    k[axis_i] = float(k_axis)
    return (
        (float(target[0]), float(target[1]), float(target[2])),
        (float(k[0]), float(k[1]), float(k[2])),
    )
