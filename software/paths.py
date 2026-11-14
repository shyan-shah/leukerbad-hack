"""Straight reach paths, minimum-jerk progress and the lead target (package S0c).

Pure functions on arrays. No robot, no API, no database.

Conventions (context/KICKOFF.md, "Shared conventions"):
- Positions are metres in the robot base (world) frame.
- A straight reach is ``start`` (3,) to ``end`` (3,);
  ``axis = (end - start) / |end - start|``.
- Progress ``s`` is the projection of ``pos - start`` on ``axis`` divided by
  the reach length (0 at start, 1 at end).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["LinePath", "min_jerk", "lead_target"]


def _as_point(a, name: str) -> np.ndarray:
    """Return ``a`` as a finite float (3,) array, else raise ValueError."""
    arr = np.asarray(a, dtype=float)
    if arr.shape != (3,):
        raise ValueError(f"{name} must have shape (3,), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be finite, got {arr}")
    return arr


@dataclass(frozen=True)
class LinePath:
    """Straight segment from ``start`` to ``end`` (metres, world frame)."""

    start: tuple[float, float, float]
    end: tuple[float, float, float]

    def _start(self) -> np.ndarray:
        return _as_point(self.start, "start")

    def _end(self) -> np.ndarray:
        return _as_point(self.end, "end")

    def length(self) -> float:
        """Distance from start to end, metres."""
        return float(np.linalg.norm(self._end() - self._start()))

    def axis(self) -> np.ndarray:
        """Unit vector from start to end. Raises ValueError for a zero-length path."""
        d = self._end() - self._start()
        n = float(np.linalg.norm(d))
        if n < 1e-9:
            raise ValueError("path has zero length, start and end coincide")
        return d / n

    def point_at(self, s: float) -> np.ndarray:
        """Point at progress ``s`` along the path, with ``s`` clamped to 0..1."""
        s = float(np.clip(s, 0.0, 1.0))
        a = self._start()
        return a + s * (self._end() - a)

    def closest(self, pos) -> tuple[np.ndarray, float, float]:
        """Closest point on the segment to ``pos``.

        Returns ``(point, s, distance)``: ``s`` is the progress of that point,
        clamped to 0..1; ``distance`` is metres from ``pos`` to it. Beside the
        segment that is the perpendicular distance to the line; beyond either
        end it is the distance to that end point.
        """
        p = _as_point(pos, "pos")
        length = self.length()
        if length < 1e-9:
            raise ValueError("path has zero length, start and end coincide")
        s = float(np.dot(p - self._start(), self.axis()) / length)
        s = float(np.clip(s, 0.0, 1.0))
        point = self.point_at(s)
        return point, s, float(np.linalg.norm(p - point))


def min_jerk(s0: float, s1: float, duration_s: float, t: float) -> float:
    """Minimum-jerk progress from ``s0`` to ``s1`` over ``duration_s`` seconds.

    ``s0 + (s1 - s0) * (10 tau^3 - 15 tau^4 + 6 tau^5)`` with ``tau = t / duration_s``
    (Flash and Hogan 1985). Velocity and acceleration are zero at both ends.
    ``t`` is clamped: before 0 gives ``s0``, after ``duration_s`` gives ``s1``.
    """
    if not duration_s > 0:
        raise ValueError(f"duration_s must be > 0, got {duration_s}")
    tau = float(np.clip(t / duration_s, 0.0, 1.0))
    return float(s0 + (s1 - s0) * (10 * tau**3 - 15 * tau**4 + 6 * tau**5))


def lead_target(path: LinePath, pos, lead_m: float, max_lead_m: float = 0.05) -> np.ndarray:
    """Point on ``path`` ``lead_m`` metres ahead of the hand's closest point.

    Negative ``lead_m`` puts the target behind the hand. The offset is capped to
    ``max_lead_m`` either way, and the target never goes past the path ends.
    """
    if not max_lead_m >= 0:
        raise ValueError(f"max_lead_m must be >= 0, got {max_lead_m}")
    _, s, _ = path.closest(pos)
    lead = float(np.clip(lead_m, -max_lead_m, max_lead_m))
    return path.point_at(s + lead / path.length())
