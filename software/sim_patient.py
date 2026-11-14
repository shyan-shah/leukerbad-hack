"""Simulated hand and patient (package S0d).

A fake hand so the control software can be developed with no robot. The
hand is a point mass of 1.5 kg with viscous damping 8 N s/m, pulled by two
forces:

- the arm's spring ``k * (target - pos)`` per base axis, and
- the patient's own effort (:meth:`SimPatient.effort`).

Pure numpy, no robot, no API, no database. Everything produced here is
simulated: :func:`simulate_reach` returns ``"simulated": True`` alongside its
arrays so the flag can be carried to the screen (KICKOFF rule 7).

Conventions (context/KICKOFF.md, "Shared conventions"): seconds, metres,
newtons; positions in the robot base frame; ``force`` is the force the person
applies to the handle; 100 Hz by default (``dt = 0.01``).

The PD gains, cap, reach and dwell timings are team-chosen simulation
parameters, not measured values.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from software.paths import LinePath, lead_target, min_jerk

__all__ = ["SimPatient", "simulate_reach", "HAND_MASS_KG", "HAND_DAMPING_NS_M"]

HAND_MASS_KG = 1.5
HAND_DAMPING_NS_M = 8.0

TREMOR_HZ = 5.0
EFFORT_CAP_N = 25.0
PATIENT_KP_N_M = 150.0    # patient's pull toward the goal, N per metre of error
PATIENT_KD_NS_M = 5.0     # patient's own damping on hand velocity


def _vec3(x, name: str) -> np.ndarray:
    a = np.asarray(x, dtype=float).reshape(-1)
    if a.shape != (3,):
        raise ValueError(f"{name} must have 3 elements, got shape {np.shape(x)}")
    return a


@dataclass
class SimPatient:
    """Simulated patient holding the handle.

    strength: 0 = limp arm, 1 = healthy.
    tremor_n: amplitude (N) of 5 Hz force noise, per axis.
    seed: fixes the tremor phases, so output is deterministic.
    present: True while a hand is on the handle. When False the patient
        applies no force at all (used by SimArm and the engine's hands-off rule).
    """

    strength: float = 1.0
    tremor_n: float = 0.0
    seed: int = 0
    present: bool = True

    def _tremor_phase(self) -> np.ndarray:
        return np.random.default_rng(self.seed).uniform(0.0, 2.0 * np.pi, size=3)

    def effort(self, t, pos, vel, goal) -> np.ndarray:
        """Force (N, shape (3,)) the patient applies to the handle.

        ``strength * PD pull toward goal`` with the pull's magnitude capped at
        25 N, plus a 5 Hz tremor of amplitude ``tremor_n`` on each axis.
        Zero when the patient is not present.
        """
        if not self.present:
            return np.zeros(3)
        pos = _vec3(pos, "pos")
        vel = _vec3(vel, "vel")
        goal = _vec3(goal, "goal")

        pull = PATIENT_KP_N_M * (goal - pos) - PATIENT_KD_NS_M * vel
        mag = float(np.linalg.norm(pull))
        if mag > EFFORT_CAP_N:
            pull *= EFFORT_CAP_N / mag
        f = self.strength * pull

        if self.tremor_n:
            f = f + self.tremor_n * np.sin(
                2.0 * np.pi * TREMOR_HZ * float(t) + self._tremor_phase()
            )
        return f


def simulate_reach(
    patient: SimPatient,
    start,
    end,
    n_reps: int,
    k_xyz,
    lead_m: float,
    dt: float = 0.01,
    *,
    reach_s: float = 1.5,
    dwell_s: float = 0.5,
) -> dict:
    """Integrate the hand for ``n_reps`` out-and-back reaches.

    Each rep is: out (``reach_s``), dwell at the end (``dwell_s``), back
    (``reach_s``), dwell at the start (``dwell_s``). The patient aims at a
    minimum-jerk goal moving along the line on that schedule. The arm's target
    is on the line, ``lead_m`` ahead of the hand's closest point in the
    current direction of travel, never beyond the line's ends
    (``software.paths.lead_target``). The arm pulls
    with spring stiffness ``k_xyz`` (N/m per base axis). The hand starts at
    rest at ``start``. Semi-implicit Euler integration at step ``dt``.

    Returns ``{"t", "pos", "vel", "force", "target"}`` as numpy arrays of
    shapes (N,), (N, 3), (N, 3), (N, 3), (N, 3), where ``force`` is the
    patient's effort (the force applied to the handle), plus
    ``"simulated": True``.
    """
    start = _vec3(start, "start")
    end = _vec3(end, "end")
    k = _vec3(k_xyz, "k_xyz")
    if np.linalg.norm(end - start) <= 0.0:
        raise ValueError("start and end must differ")
    if int(n_reps) != n_reps or n_reps < 1:
        raise ValueError("n_reps must be a positive integer")
    if dt <= 0 or reach_s <= 0 or dwell_s < 0:
        raise ValueError("dt and reach_s must be > 0, dwell_s >= 0")
    if np.any(k < 0):
        raise ValueError("k_xyz must be >= 0")

    rep_s = 2.0 * (reach_s + dwell_s)
    n = int(round(n_reps * rep_s / dt))
    t_arr = np.arange(n) * dt
    pos_arr = np.empty((n, 3))
    vel_arr = np.empty((n, 3))
    force_arr = np.empty((n, 3))
    target_arr = np.empty((n, 3))

    pos = start.copy()
    vel = np.zeros(3)
    d = end - start
    path = LinePath(tuple(start), tuple(end))
    lead = abs(float(lead_m))

    for i in range(n):
        t = float(t_arr[i])
        tr = t % rep_s
        if tr < reach_s + dwell_s:                     # out, then dwell at end
            s_goal = min_jerk(0.0, 1.0, reach_s, tr)
            signed_lead = lead
        else:                                          # back, then dwell at start
            s_goal = min_jerk(1.0, 0.0, reach_s, tr - reach_s - dwell_s)
            signed_lead = -lead
        goal = start + s_goal * d

        # max_lead_m = lead so the target leads by exactly lead_m; SimArm applies
        # the arm's own lead clamp on top of this.
        target = lead_target(path, pos, signed_lead, max_lead_m=lead)
        f_patient = patient.effort(t, pos, vel, goal)

        pos_arr[i] = pos
        vel_arr[i] = vel
        force_arr[i] = f_patient
        target_arr[i] = target

        f_total = k * (target - pos) + f_patient - HAND_DAMPING_NS_M * vel
        vel = vel + (f_total / HAND_MASS_KG) * dt
        pos = pos + vel * dt

    return {
        "t": t_arr,
        "pos": pos_arr,
        "vel": vel_arr,
        "force": force_arr,
        "target": target_arr,
        "simulated": True,
    }
