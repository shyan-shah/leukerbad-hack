"""The data contract between the engine (software/) and the server (server/).

Shiv's engine produces these records; the server stores and serves them.
Fields may be added (with defaults, at the end), never renamed or removed.
See context/MASTER_PLAN.md sections 4.5 and KICKOFF "Shared conventions".

Units: seconds, metres, newtons. Positions in the robot base frame.
`force` is the force the person applies to the handle.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


def _plain(v: Any) -> Any:
    """Convert tuples/lists and numpy scalars to plain JSON types."""
    if isinstance(v, (tuple, list)):
        return [_plain(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        return v.item()  # numpy scalar
    return v


class _Record:
    def to_dict(self) -> dict[str, Any]:
        return {f.name: _plain(getattr(self, f.name)) for f in fields(self)}  # type: ignore[arg-type]

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        kwargs = {}
        for f in fields(cls):  # type: ignore[arg-type]
            if f.name not in d:
                continue  # missing field: dataclass default applies (or TypeError if required)
            v = d[f.name]
            if "tuple" in str(f.type) and isinstance(v, list):
                v = tuple(v)
            kwargs[f.name] = v
        return cls(**kwargs)


@dataclass(frozen=True)
class Sample(_Record):
    """One 100 Hz tick."""
    t: float                                  # s since session start
    pos: tuple[float, float, float]
    vel: tuple[float, float, float]
    force: tuple[float, float, float]
    target: tuple[float, float, float]        # where the arm is pulling toward
    dial: float                               # -1 full resistance .. 0 transparent .. +1 full assistance
    rep_idx: int                              # -1 between reps
    simulated: bool
    phase: str = "idle"                       # "idle" | "out" | "back" (v1) | "setup" (pull: moving to the far end)
    q: tuple[float, ...] = ()                 # 7 joint angles, rad      (v1)


@dataclass(frozen=True)
class RepResult(_Record):
    """One finished repetition."""
    session_id: str
    idx: int
    mode: str                                 # "assist" | "transparent" | "resist" | "isometric" (armtest try)
    dial: float
    t_start: float
    duration_s: float
    rom_m: float                              # range of motion along the reach axis
    path_err_mean_m: float
    path_err_max_m: float
    sparc: float                              # smoothness, more negative = less smooth
    peak_force_n: float
    mean_force_n: float
    contribution: float                       # 0..1 share of the movement done by the person (team-defined index)
    completed: bool
    simulated: bool
    rescued: bool = False                     # stall rescue fired during this rep  (v1)


@dataclass(frozen=True)
class SessionSummary(_Record):
    session_id: str
    patient_id: str
    started_at: str                           # ISO 8601
    ended_at: str | None
    exercise: str                             # programme id: "reach" | "push" | "pull" | "armtest" | "circle"
    n_reps: int
    simulated: bool
