"""Auto dial adaptation (assist as needed), MASTER_PLAN section 4.2.

After each rep in auto mode the dial D moves:
- down by STEP_DOWN (0.15) if the rep was a success,
- up by STEP_UP (0.10) if it failed,
- otherwise it stays.
The result is clamped to [auto_floor, 1.0] (auto_floor defaults to -0.6).

Success: completed, mean path error under 1.5 cm, duration under 6 s,
not rescued, and (outside the resist side) contribution over 0.6.
Failure: not completed, or contribution under 0.3, or rescued.

"Resist side" means the dial the rep was run at is negative (mode "resist").
These thresholds are team-chosen starting values, not clinical rules.
"""
from __future__ import annotations

from server.contract import RepResult

STEP_DOWN = 0.15
STEP_UP = 0.10
DIAL_MAX = 1.0
AUTO_FLOOR = -0.6

SUCCESS_PATH_ERR_M = 0.015
SUCCESS_DURATION_S = 6.0
SUCCESS_CONTRIBUTION = 0.6
FAIL_CONTRIBUTION = 0.3

_ZERO_TOL = 1e-9

__all__ = ["next_dial", "mode_of", "is_success", "is_failure"]


def mode_of(dial: float) -> str:
    """'assist' for D > 0, 'transparent' for D == 0, 'resist' for D < 0."""
    if dial > _ZERO_TOL:
        return "assist"
    if dial < -_ZERO_TOL:
        return "resist"
    return "transparent"


def is_failure(rep: RepResult) -> bool:
    return (not rep.completed) or rep.contribution < FAIL_CONTRIBUTION or rep.rescued


def is_success(rep: RepResult, dial: float) -> bool:
    if not rep.completed or rep.rescued:
        return False
    if not rep.path_err_mean_m < SUCCESS_PATH_ERR_M:
        return False
    if not rep.duration_s < SUCCESS_DURATION_S:
        return False
    if mode_of(dial) != "resist" and not rep.contribution > SUCCESS_CONTRIBUTION:
        return False
    return True


def next_dial(dial: float, rep: RepResult, auto_floor: float = AUTO_FLOOR) -> float:
    """Dial for the next rep after ``rep`` was done at ``dial``."""
    if is_failure(rep):
        new = dial + STEP_UP
    elif is_success(rep, dial):
        new = dial - STEP_DOWN
    else:
        new = dial
    new = min(DIAL_MAX, max(auto_floor, new))
    new = round(new, 6)  # keep 1.0 - 5 * 0.15 == 0.25 exactly, and 0 exactly transparent
    return 0.0 if new == 0 else new
