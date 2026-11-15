"""Exercise presets for the engine (package E1). See context/EXERCISE_MAP.md and software/EXERCISES.md.

A preset is a small, frozen set of numbers over the existing control law. ``Engine(...,
exercise="<id>")`` applies it. ``EXERCISES`` holds every preset; ``LIVE`` lists the ids the
robot runs for the pitch (the server should refuse the others).

Kinds:
- ``assist``  straight reach, assist as needed (dial > 0, auto dial).
- ``resist``  the same line against the elastic band (dial < 0).
- ``test``    isometric strength test: the handle is held still and the person pushes.
- ``guided``  robot-led shape (the target moves, the same stiffness on every axis).

``direction`` is relative to the configured reach sign (+1 = the configured reach direction,
-1 = towards the patient). ``start_at="far"`` puts the path start at the far end of the
configured reach, so the person first moves the handle there in the "setup" phase.

All numbers are team-chosen starting values, not clinical prescriptions.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ExercisePreset", "EXERCISES", "LIVE", "get", "KINDS"]

KINDS = ("assist", "resist", "test", "guided")


@dataclass(frozen=True)
class ExercisePreset:
    id: str
    name: str
    kind: str                       # "assist" | "resist" | "test" | "guided"
    reach_m: float = 0.30           # length of the line (guided: the circle's diameter)
    direction: int = 1              # +1 / -1 relative to the configured reach_sign
    start_at: str = "start"         # "start" | "far"
    dial: float = 1.0
    auto: bool = True
    default_reps: int = 10          # reps, tries or circles
    # test (isometric) fields
    push_s: float = 0.0             # s of pushing per try
    rest_s: float = 0.0             # s of rest between tries
    min_peak_n: float = 5.0         # a try counts as completed above this peak force
    max_disp_m: float = 0.05        # a push that moves the handle further than this ends the try
    # guided (circle) fields
    radius_m: float = 0.0
    period_s: float = 0.0           # s per circle
    stiffness: float = 0.0          # N/m on all three axes

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {self.kind!r}")
        if self.direction not in (1, -1):
            raise ValueError(f"direction must be +1 or -1, got {self.direction}")
        if self.start_at not in ("start", "far"):
            raise ValueError(f"start_at must be 'start' or 'far', got {self.start_at!r}")
        if (self.start_at == "far") != (self.direction == -1):
            raise ValueError("start_at 'far' goes with direction -1 and 'start' with +1 "
                             "(the line always lies between the start pose and the far end)")
        if not self.reach_m > 0:
            raise ValueError(f"reach_m must be > 0, got {self.reach_m}")
        if not -1.0 <= self.dial <= 1.0:
            raise ValueError(f"dial must be in [-1, 1], got {self.dial}")
        if self.default_reps < 1:
            raise ValueError("default_reps must be at least 1")
        if self.kind == "assist" and not self.dial > 0:
            raise ValueError("an assist preset needs dial > 0")
        if self.kind == "resist" and not self.dial < 0:
            raise ValueError("a resist preset needs dial < 0")
        if self.kind == "test" and not (self.push_s > 0 and self.rest_s >= 0):
            raise ValueError("a test preset needs push_s > 0 and rest_s >= 0")
        if self.kind == "guided" and not (self.radius_m > 0 and self.period_s > 0 and self.stiffness > 0):
            raise ValueError("a guided preset needs radius_m, period_s and stiffness > 0")


EXERCISES: dict[str, ExercisePreset] = {p.id: p for p in (
    ExercisePreset("reach", "Forward reach (assisted)", "assist",
                   reach_m=0.30, direction=1, start_at="start", dial=1.0, auto=True, default_reps=10),
    ExercisePreset("push", "Push (resisted)", "resist",
                   reach_m=0.28, direction=1, start_at="start", dial=-0.3, auto=False, default_reps=10),
    ExercisePreset("pull", "Row (resisted)", "resist",
                   reach_m=0.28, direction=-1, start_at="far", dial=-0.3, auto=False, default_reps=10),
    ExercisePreset("armtest", "Push strength test", "test",
                   reach_m=0.30, dial=0.0, auto=False, default_reps=3, push_s=3.0, rest_s=5.0),
    ExercisePreset("circle", "Circle (robot-led)", "guided",
                   reach_m=0.16, dial=0.0, auto=False, default_reps=8,
                   radius_m=0.08, period_s=6.0, stiffness=300.0),
)}

LIVE: tuple[str, ...] = ("reach", "push", "pull", "armtest")     # circle is a stretch, SimArm only


def get(exercise: str) -> ExercisePreset:
    """Preset by id. Raises ValueError naming the known ids."""
    try:
        return EXERCISES[exercise]
    except KeyError:
        raise ValueError(f"unknown exercise {exercise!r}; known: {sorted(EXERCISES)}") from None
