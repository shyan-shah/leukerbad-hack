"""Repetition detection for straight reaches (package S0b).

A rep is one out-and-back reach along the line from `start` to `end`.
Progress `s` is the projection of `pos - start` on the reach axis divided by
the reach length (0 at start, 1 at end), as in the shared conventions.

Rules, shared by `segment_reps` (offline) and `RepDetector` (live):

- A rep starts on the first sample where `s` rises above `back_thresh`.
- It counts as completed if `s` reaches `out_thresh` before it ends.
- It ends on the first sample where `s` falls back under `back_thresh`.
- An excursion shorter than `min_duration_s` (end time minus start time) is
  threshold jitter, not a rep, and is discarded.
- An excursion still open when the recording stops is not returned.

Units: seconds and metres. Pure functions on arrays, no I/O.
"""

from __future__ import annotations

import numpy as np


def _line(start, end) -> tuple[np.ndarray, np.ndarray, float]:
    start = np.asarray(start, dtype=float).reshape(3)
    end = np.asarray(end, dtype=float).reshape(3)
    length = float(np.linalg.norm(end - start))
    if length < 1e-9:
        raise ValueError("start and end must be different points")
    return start, (end - start) / length, length


def progress(pos, start, end) -> np.ndarray:
    """Progress `s` along the reach for each sample, unclamped.

    pos: (N, 3) or (3,) positions in metres. Returns shape (N,) (or a 0-d
    array for a single (3,) position). 0 at `start`, 1 at `end`, can go
    below 0 or above 1.
    """
    start, axis, length = _line(start, end)
    pos = np.asarray(pos, dtype=float)
    if pos.shape[-1] != 3:
        raise ValueError(f"pos must have 3 columns, got shape {pos.shape}")
    return (pos - start) @ axis / length


class RepDetector:
    """Live rep detector: same logic as `segment_reps`, one sample at a time.

    `update(t, pos)` returns:
      "rep_start"   when s rises above back_thresh,
      "rep_reached" once per rep, when s first reaches out_thresh,
      "rep_end"     when s falls under back_thresh and the rep lasted at
                    least min_duration_s,
      None          otherwise. A too-short excursion (jitter) also returns
                    None when it closes: it is dropped, `in_rep` goes back to
                    False and nothing is added to `reps`.

    Attributes: `in_rep` (bool), `reached` (bool, current rep),
    `i_start` / `t_start` (current rep), `n` (samples seen) and `reps`, the
    list of finished (i_start, i_end, completed) tuples with sample indices
    counted from the first `update` call.
    """

    def __init__(self, start, end, out_thresh=0.9, back_thresh=0.1, min_duration_s=0.5):
        if not back_thresh < out_thresh:
            raise ValueError("back_thresh must be below out_thresh")
        self.start, self.end = start, end
        self._start, self._axis, self._length = _line(start, end)
        self.out_thresh = float(out_thresh)
        self.back_thresh = float(back_thresh)
        self.min_duration_s = float(min_duration_s)
        self.reset()

    def reset(self) -> None:
        self.n = 0
        self.in_rep = False
        self.reached = False
        self.i_start = -1
        self.t_start = float("nan")
        self.reps: list[tuple[int, int, bool]] = []

    def update(self, t: float, pos) -> str | None:
        p = np.asarray(pos, dtype=float).reshape(3)
        s = float((p - self._start) @ self._axis / self._length)
        i = self.n
        self.n += 1
        event = None
        if not self.in_rep:
            if s > self.back_thresh:
                self.in_rep = True
                self.reached = False
                self.i_start = i
                self.t_start = float(t)
                event = "rep_start"
                if s >= self.out_thresh:  # very coarse sampling: start and reach on one tick
                    self.reached = True
            return event
        if not self.reached and s >= self.out_thresh:
            self.reached = True
            return "rep_reached"
        if s < self.back_thresh:
            keep = float(t) - self.t_start >= self.min_duration_s
            if keep:
                self.reps.append((self.i_start, i, self.reached))
            self.in_rep = False
            self.reached = False
            self.i_start = -1
            self.t_start = float("nan")
            return "rep_end" if keep else None
        return None


def segment_reps(t, pos, start, end, out_thresh=0.9, back_thresh=0.1,
                 min_duration_s=0.5) -> list[tuple[int, int, bool]]:
    """Split a recording into reps.

    t: (N,) seconds, pos: (N, 3) metres. Returns a list of
    (i_start, i_end, completed): i_start is the first sample above
    back_thresh, i_end the first sample back under it. Same rules as
    `RepDetector`, see the module docstring.
    """
    t = np.asarray(t, dtype=float).reshape(-1)
    pos = np.asarray(pos, dtype=float)
    if pos.ndim != 2 or pos.shape[1] != 3:
        raise ValueError(f"pos must have shape (N, 3), got {pos.shape}")
    if len(t) != len(pos):
        raise ValueError("t and pos must have the same length")
    if not back_thresh < out_thresh:
        raise ValueError("back_thresh must be below out_thresh")
    s = progress(pos, start, end)
    above = s > back_thresh
    reps: list[tuple[int, int, bool]] = []
    i = 0
    n = len(s)
    while i < n:
        if not above[i]:
            i += 1
            continue
        i0 = i
        # first sample at or after i0 + 1 that falls under back_thresh
        under = np.flatnonzero(s[i0 + 1:] < back_thresh)
        if under.size == 0:
            break  # still out when the recording stops: not a finished rep
        i1 = i0 + 1 + int(under[0])
        if t[i1] - t[i0] >= min_duration_s:
            reps.append((i0, i1, bool(np.any(s[i0:i1] >= out_thresh))))
        i = i1 + 1
    return reps
