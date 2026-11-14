"""Per-repetition movement metrics (package S0a).

Pure functions on arrays. No robot, no API, no database.

Conventions (context/KICKOFF.md, "Shared conventions"):
- ``t`` shape (N,), seconds, increasing.
- ``pos`` shape (N, 3), metres, handle position in the robot base frame.
- ``force`` shape (N, 3), newtons, force the person applies to the handle.
- A straight reach is ``start`` (3,) to ``end`` (3,);
  ``axis = (end - start) / |end - start|``.

The keys returned by :func:`rep_metrics` are named as the fields of
``server.contract.RepResult``.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "rom",
    "path_error",
    "force_stats",
    "sparc",
    "contribution",
    "rep_metrics",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _as_points(a, name: str) -> np.ndarray:
    """Return ``a`` as a float (N, 3) array with N >= 2, else raise ValueError."""
    arr = np.asarray(a, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError(f"{name} must have shape (N, 3), got {arr.shape}")
    if arr.shape[0] < 2:
        raise ValueError(f"{name} needs at least 2 samples, got {arr.shape[0]}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains NaN or inf")
    return arr


def _reach(start, end) -> tuple[np.ndarray, np.ndarray, float]:
    """Return (start, unit axis, length) for a straight reach."""
    s = np.asarray(start, dtype=float).reshape(-1)
    e = np.asarray(end, dtype=float).reshape(-1)
    if s.shape != (3,) or e.shape != (3,):
        raise ValueError("start and end must each have 3 elements")
    length = float(np.linalg.norm(e - s))
    if length < 1e-9:
        raise ValueError("start and end must be different points")
    return s, (e - s) / length, length


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def rom(pos, start, end) -> float:
    """Range of motion along the reach axis, in metres.

    Max minus min of the (unclamped) distance travelled along the axis,
    i.e. of ``dot(pos - start, axis)``.
    """
    p = _as_points(pos, "pos")
    s, axis, _ = _reach(start, end)
    along = (p - s) @ axis
    return float(along.max() - along.min())


VERTICAL_AXIS = 2   # base z is up (the arm is mounted upright)


def path_error(pos, start, end, remove_vertical_sag: bool = True) -> tuple[float, float]:
    """(mean, max) perpendicular distance from ``pos`` to the reach line, metres.

    With ``remove_vertical_sag`` (default) the mean vertical (base z) part of the
    perpendicular offset over the slice is subtracted first. The limb's weight rests on
    the across-path wall spring and sags the handle by a constant amount (8 N on
    K_WALL 500 N/m is 1.6 cm), which is the device's compliance, not the person's
    control, and on its own exceeded the 1.5 cm success limit. Vertical wobble around
    that mean and every sideways offset still count. See DECISIONS.md.
    """
    p = _as_points(pos, "pos")
    s, axis, _ = _reach(start, end)
    rel = p - s
    perp = rel - np.outer(rel @ axis, axis)
    if remove_vertical_sag:
        perp[:, VERTICAL_AXIS] -= perp[:, VERTICAL_AXIS].mean()
    d = np.linalg.norm(perp, axis=1)
    return float(d.mean()), float(d.max())


def force_stats(force) -> tuple[float, float]:
    """(peak, mean) of the force magnitude, newtons."""
    f = _as_points(force, "force")
    mag = np.linalg.norm(f, axis=1)
    return float(mag.max()), float(mag.mean())


def sparc(speed, fs, padlevel=4, fc=10.0, amp_th=0.05) -> float:
    """Spectral arc length (SPARC) smoothness of a speed profile.

    More negative means less smooth.

    Port of ``sparc`` in ``scripts/smoothness.py`` of the reference
    implementation, https://github.com/siva82kb/SPARC
    (raw: https://raw.githubusercontent.com/siva82kb/SPARC/master/scripts/smoothness.py),
    from Balasubramanian, Melendez-Calderon, Roby-Brami, Burdet (2015),
    "On the analysis of movement smoothness", J NeuroEngineering Rehabil
    12:112. The computation is line-for-line the same as the reference; the
    only differences are input validation and that this returns just the
    arc length (the reference also returns the spectra).

    Parameters
    ----------
    speed : array (N,)
        Movement speed profile (magnitude of velocity), m/s.
    fs : float
        Sampling frequency, Hz.
    padlevel : int
        Amount of zero padding for the FFT. [default 4]
    fc : float
        Maximum cut-off frequency for the arc length, Hz. [default 10.0]
    amp_th : float
        Amplitude threshold that sets the adaptive cut-off. [default 0.05]
    """
    movement = np.asarray(speed, dtype=float).reshape(-1)
    if movement.size < 2:
        raise ValueError(f"speed needs at least 2 samples, got {movement.size}")
    if not np.all(np.isfinite(movement)):
        raise ValueError("speed contains NaN or inf")
    if not fs > 0:
        raise ValueError("fs must be positive")
    if not np.any(movement != 0):
        raise ValueError("speed is zero everywhere: SPARC is undefined")

    # Number of zeros to be padded.
    nfft = int(pow(2, np.ceil(np.log2(len(movement))) + padlevel))

    # Frequency
    f = np.arange(0, fs, fs / nfft)
    # Normalized magnitude spectrum
    Mf = abs(np.fft.fft(movement, nfft))
    Mf = Mf / max(Mf)

    # Indices to choose only the spectrum within the given cut off frequency
    # Fc. (Low pass step so high frequency noise does not affect the
    # amplitude threshold based cut off below.)
    fc_inx = ((f <= fc) * 1).nonzero()
    f_sel = f[fc_inx]
    Mf_sel = Mf[fc_inx]

    # Choose the amplitude threshold based cut off frequency.
    # Index of the last point on the magnitude spectrum that is greater than
    # or equal to the amplitude threshold.
    inx = ((Mf_sel >= amp_th) * 1).nonzero()[0]
    fc_inx = range(inx[0], inx[-1] + 1)
    f_sel = f_sel[fc_inx]
    Mf_sel = Mf_sel[fc_inx]

    # Calculate arc length
    new_sal = -sum(np.sqrt(pow(np.diff(f_sel) / (f_sel[-1] - f_sel[0]), 2) +
                           pow(np.diff(Mf_sel), 2)))
    return float(new_sal)


def contribution(force, vel, start, end, dt: float = 0.01, robot_force=None) -> float:
    """Share of the movement done by the person, 0..1.

    Team-defined index, not a clinically validated measure.

    ``f`` is the person's force projected on the reach axis and ``v`` the
    hand velocity projected on it. Person's work ``Wp = sum(max(0, f*v))*dt``.
    Robot's work ``Wr``:

    - ``robot_force`` not given (original S0a rule): ``Wr = sum(max(0, -f*v))*dt``,
      i.e. robot work is inferred only when the person's force opposes the motion.
    - ``robot_force`` given, shape (N, 3), the arm's force on the hand (for the
      impedance arm the commanded spring ``K * (target - hand)`` per axis):
      ``Wr = sum(max(0, fr*v))*dt`` with ``fr`` its projection on the reach axis.
      This counts the arm's own positive work, so a patient pushing lightly while
      the arm carries them is no longer scored about 1. The inferred term above
      is not added, so nothing is counted twice.

    Returns ``Wp / (Wp + Wr)``, or 0.0 if both are under 1e-6 J. ``dt`` defaults
    to the 100 Hz convention.
    """
    fo = _as_points(force, "force")
    ve = _as_points(vel, "vel")
    if fo.shape != ve.shape:
        raise ValueError(f"force {fo.shape} and vel {ve.shape} must have the same shape")
    _, axis, _ = _reach(start, end)
    v = ve @ axis
    p = (fo @ axis) * v
    wp = float(np.sum(np.maximum(0.0, p)) * dt)
    if robot_force is None:
        wr = float(np.sum(np.maximum(0.0, -p)) * dt)
    else:
        fr = _as_points(robot_force, "robot_force")
        if fr.shape != ve.shape:
            raise ValueError(f"robot_force {fr.shape} and vel {ve.shape} must have the same shape")
        wr = float(np.sum(np.maximum(0.0, (fr @ axis) * v)) * dt)
    if wp < 1e-6 and wr < 1e-6:
        return 0.0
    return wp / (wp + wr)


def rep_metrics(t, pos, force, start, end, robot_force=None) -> dict:
    """All metrics for one repetition, keys named as in ``RepResult``.

    Returns ``duration_s, rom_m, path_err_mean_m, path_err_max_m, sparc,
    peak_force_n, mean_force_n, contribution``. Velocity is
    ``numpy.gradient(pos, t)``; SPARC uses its magnitude (speed) with
    ``fs = 1 / median(diff(t))``. ``robot_force`` (optional, (N, 3)) is passed
    to :func:`contribution`.
    """
    tt = np.asarray(t, dtype=float).reshape(-1)
    p = _as_points(pos, "pos")
    f = _as_points(force, "force")
    if tt.size != p.shape[0] or tt.size != f.shape[0]:
        raise ValueError("t, pos and force must have the same number of samples")
    dts = np.diff(tt)
    if not np.all(dts > 0):
        raise ValueError("t must be strictly increasing")

    vel = np.gradient(p, tt, axis=0)
    speed = np.linalg.norm(vel, axis=1)
    dt = float(np.median(dts))

    err_mean, err_max = path_error(p, start, end)
    peak, mean = force_stats(f)
    return {
        "duration_s": float(tt[-1] - tt[0]),
        "rom_m": rom(p, start, end),
        "path_err_mean_m": err_mean,
        "path_err_max_m": err_max,
        "sparc": sparc(speed, 1.0 / dt),
        "peak_force_n": peak,
        "mean_force_n": mean,
        "contribution": contribution(f, vel, start, end, dt=dt, robot_force=robot_force),
    }
