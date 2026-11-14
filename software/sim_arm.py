"""Simulated arm behind the frozen interface of MASTER_PLAN section 4.3 (package S1).

``SimArm`` exposes the same names and behaviour as ``robot.arm.Arm`` with no robot
and no RDK, so the engine, server and screens can be built and tested anywhere.
Everything it produces is simulated (KICKOFF rule 7).

Physics (per base axis, semi-implicit Euler, substeps of at most 5 ms):

    m * a = k * (target - pos) + F_person - c * vel

- ``m = 1.5 kg``, ``c = 8 N s/m`` (``software.sim_patient`` constants).
- ``k`` is the commanded per-axis stiffness, ``target`` the last accepted target.
- ``F_person`` is the force the person applies to the handle and is also what
  ``get_state().force`` reports: the patient's effort toward their current goal
  (``SimPatient.effort``) plus a passive limb load while ``patient.present`` is
  true (8 N downward plus 5 N s/m drag against motion). Zero when the handle is
  empty, so the engine's hands-off rule can be tested.

Safety behaviour is shared with the real arm, not re-implemented: target and
stiffness clamps and the trip checks are ``robot.arm.clamp_target``,
``clamp_stiffness`` and ``check_trip``. The watchdog runs on the sim clock.
Stiffness changes take effect ``STIFFNESS_LATENCY_S`` after the call (latest
value wins), like the real arm's worker thread.

Patient intent: the simulated person follows a simple out-and-back routine
along the reach (rest at the start, a minimum-jerk reach over ``PATIENT_REACH_S``,
a short dwell, a minimum-jerk return). The reach is ``reach_axis`` /
``reach_sign`` / ``reach_m`` (attributes, defaults x, +1, 0.30 m).

- Cue: the reach starts when the applied stiffness leaves the all-axes
  ``k_hold`` soft hold, which is what the engine does when it arms a rep (a
  therapist saying "go"). The cue overrides whatever the patient was doing.
  Stiffness changes that do not start from the soft hold (rescue, dial changes
  mid-rep) are not a cue. Before the first cue, the patient starts a reach on
  its own after resting ``PATIENT_REST_S`` at the start (for use without an
  engine).
- The reach aims ``PATIENT_OVERSHOOT`` of the way along the line (past the end,
  "reaching through the target") so a strong patient still completes a reach
  against resistance. It counts as arrived at ``PATIENT_END_PROGRESS``, the same
  progress at which the engine starts its back phase, and the goal then
  settles at the end of the line (it never goes on to the overshoot point).
- "At the start" is measured along the reach axis only, like the engine, so the
  limb load sagging the handle does not hide it.
- Phase changes otherwise wait for the hand to arrive (with a timeout), so a
  weak patient keeps trying while the arm helps.

The timings and the overshoot are team-chosen simulation parameters, not
measured values.

Not simulated: joint angles (``q`` is seven zeros), orientation (fixed at the
start orientation), robot-side velocity limits and faults.

Clocks: ``ArmState.t`` is on a ``time.monotonic()`` base. With
``realtime=True`` a 100 Hz background thread (started by ``connect()``)
advances the sim on wall time. With ``realtime=False`` nothing moves until
``step(dt)`` is called, which is how the tests run fast and deterministically.
"""

from __future__ import annotations

import math
import threading
import time

import numpy as np

from robot.arm import ArmState, Limits, check_trip, clamp_stiffness, clamp_target
from software.paths import min_jerk
from software.sim_patient import HAND_DAMPING_NS_M, HAND_MASS_KG, SimPatient

__all__ = ["SimArm"]

TICK_S = 0.01                    # realtime thread period, 100 Hz
MAX_SUBSTEP_S = 0.005            # integration substep
STIFFNESS_LATENCY_S = 0.05       # set_stiffness takes effect after this (real arm: about 100 ms max)

PASSIVE_LOAD_N = 8.0             # limb weight on the handle, downward (-z), while present
PASSIVE_DRAG_NS_M = 5.0          # limb drag against motion, while present

PATIENT_REACH_S = 3.0            # min-jerk reach time out and back (peak 0.19 m/s over 0.30 m)
PATIENT_REST_S = 1.5             # rest near the start before reaching again (engine arms after 1.0 s)
PATIENT_DWELL_S = 0.5            # pause at the end before returning
PATIENT_PHASE_TIMEOUT_S = 10.0   # give up waiting for the hand and move on
PATIENT_END_PROGRESS = 0.90      # hand progress counted as "arrived" (= engine's OUT_DONE)
PATIENT_NEAR_START_M = 0.02      # distance along the reach counted as "back at the start"
PATIENT_OVERSHOOT = 1.3          # the reach aims this far along the line (1.0 = the end)

DEFAULT_QUAT = (0.0, 0.0, 1.0, 0.0)   # matches the robot/config.json start orientation
ZERO_Q = (0.0,) * 7


class SimArm:
    """Simulated arm with the section 4.3 interface. See the module docstring."""

    limits: Limits
    start_pos: tuple[float, float, float]

    def __init__(self, patient: SimPatient, limits: Limits = Limits(),
                 start_pos=(0.45, 0.0, 0.30), realtime: bool = True) -> None:
        self.patient = patient
        self.limits = limits
        self.start_pos = tuple(float(v) for v in start_pos)  # type: ignore[assignment]
        if len(self.start_pos) != 3:
            raise ValueError("start_pos must have 3 elements")
        self.start_quat = DEFAULT_QUAT
        self.realtime = bool(realtime)
        self.reach_axis = 0
        self.reach_sign = 1
        self.reach_m = 0.30

        self._lock = threading.RLock()
        self._connected = False
        self._started = False
        self._mode = "idle"
        self._fault: str | None = None

        self._t = time.monotonic()
        self._pos = np.array(self.start_pos, dtype=float)
        self._vel = np.zeros(3)
        self._target = self._pos.copy()
        self._k = np.full(3, float(limits.k_hold))
        self._k_pending: tuple[np.ndarray, float] | None = None
        self._last_target_t = self._t

        # patient intent: "rest" -> "out" -> "dwell" -> "back" -> "rest"
        self._intent = "rest"
        self._intent_t0 = self._t
        self._near_start_since: float | None = None
        self._cued = False            # True once an engine cue has been seen
        self._s_from = 0.0            # progress the dwell/back starts from

        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ connection and setup

    def connect(self) -> None:
        """Mark connected; with realtime=True start the 100 Hz physics thread."""
        with self._lock:
            self._connected = True
            self._mode, self._fault = "idle", None
            self._t = time.monotonic()
            self._intent_t0 = self._t
            self._last_target_t = self._t
        if self.realtime and self._thread is None:
            self._running = True
            self._thread = threading.Thread(target=self._realtime_loop, name="simarm-physics",
                                            daemon=True)
            self._thread.start()

    def _require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("SimArm is not connected; call connect() first")

    def zero_force(self) -> None:
        """Sim force sensor has no offset; leaves mode "idle"."""
        self._require_connected()
        with self._lock:
            self._k_pending = None
            self._mode = "idle"

    def home(self) -> None:
        """Put the hand at start_pos at rest. Nobody holding. Leaves mode "idle"."""
        self._require_connected()
        with self._lock:
            self._k_pending = None
            self._mode = "idle"
            self._pos = np.array(self.start_pos, dtype=float)
            self._vel = np.zeros(3)
            self._target = self._pos.copy()

    def start_compliance(self) -> None:
        """Hold the current pose at k_hold and accept commands. Re-arms after a trip."""
        self._require_connected()
        with self._lock:
            self._k_pending = None
            self._k = np.full(3, float(self.limits.k_hold))
            self._target = self._pos.copy()
            self._last_target_t = self._t
            self._fault = None
            self._mode = "compliant"
            self._started = True

    # ------------------------------------------------------------------ live commands

    def _check_commandable(self, what: str) -> bool:
        if not self._started:
            raise RuntimeError(f"{what}() before start_compliance()")
        return self._mode == "compliant"

    def set_stiffness(self, kx: float, ky: float, kz: float) -> None:
        """N/m per base axis, clamped to [0, k_max]. Takes effect after STIFFNESS_LATENCY_S."""
        if not self._check_commandable("set_stiffness"):
            return
        k = np.array(clamp_stiffness((kx, ky, kz), self.limits), dtype=float)
        with self._lock:
            if self._mode == "compliant":
                self._k_pending = (k, self._t + STIFFNESS_LATENCY_S)

    def set_target(self, pos: tuple[float, float, float]) -> None:
        """Clamped to the box, then to max_lead_m from the hand. Feeds the watchdog."""
        if not self._check_commandable("set_target"):
            return
        with self._lock:
            if self._mode != "compliant":
                return
            t = clamp_target(pos, tuple(self._pos), self.start_pos, self.limits)
            self._target = np.array(t, dtype=float)
            self._last_target_t = self._t

    def get_state(self) -> ArmState:
        """Fresh state. While compliant, also runs the trip checks (speed, force, box)."""
        self._require_connected()
        with self._lock:
            pos = tuple(float(v) for v in self._pos)
            vel = tuple(float(v) for v in self._vel)
            force = tuple(float(v) for v in self._person_force(self._t, self._pos, self._vel))
            if self._mode == "compliant":
                reason = check_trip(pos, vel, force, self.start_pos, self.limits)
                if reason is not None:
                    self._trip(reason)
            return ArmState(self._t, pos, self.start_quat, vel, force, ZERO_Q,  # type: ignore[arg-type]
                            self._mode, self._fault)

    # ------------------------------------------------------------------ stops

    def _trip(self, reason: str) -> None:
        with self._lock:
            self._fault = reason
            self._hold_locked()

    def _hold_locked(self) -> None:
        self._k_pending = None
        self._target = self._pos.copy()
        self._k = np.full(3, float(self.limits.k_hold))
        self._mode = "hold"

    def hold(self) -> None:
        """Soft stop: target = current position, k_hold on all axes, mode "hold"."""
        with self._lock:
            self._hold_locked()

    def stop(self) -> None:
        """Hard stop: the hand is frozen in place, mode "idle"."""
        with self._lock:
            self._k_pending = None
            self._vel = np.zeros(3)
            self._mode = "idle"

    def close(self) -> None:
        """Hold, stop, end the physics thread."""
        try:
            with self._lock:
                self._hold_locked()
        finally:
            self.stop()
            self._running = False
            th, self._thread = self._thread, None
            if th is not None and th is not threading.current_thread():
                th.join(timeout=1.0)

    # ------------------------------------------------------------------ simulation

    def step(self, dt: float) -> None:
        """Advance the simulation by dt seconds (realtime=False only)."""
        if self.realtime:
            raise RuntimeError("step() is only for SimArm(realtime=False)")
        if not dt > 0:
            raise ValueError("dt must be > 0")
        with self._lock:
            self._advance(float(dt))

    def _realtime_loop(self) -> None:
        last = time.monotonic()
        while self._running:
            time.sleep(TICK_S)
            now = time.monotonic()
            dt = min(now - last, 0.05)  # a stalled thread never takes one huge step
            last = now
            if dt > 0:
                with self._lock:
                    self._advance(dt)

    def _reach_vector(self) -> np.ndarray:
        u = np.zeros(3)
        u[self.reach_axis] = 1.0 if self.reach_sign >= 0 else -1.0
        return u * float(self.reach_m)

    def _at_hold_stiffness(self) -> bool:
        return bool(np.allclose(self._k, float(self.limits.k_hold)))

    def _set_intent(self, intent: str) -> None:
        self._intent = intent
        self._intent_t0 = self._t
        self._near_start_since = None

    def _cue_reach(self) -> None:
        """Engine cue (stiffness left the soft hold): start a reach now, whatever the state."""
        self._cued = True
        self._set_intent("out")

    def _progress(self, pos: np.ndarray) -> float:
        d = self._reach_vector()
        return float((pos - np.array(self.start_pos)) @ d / (d @ d))

    def _goal(self, t: float) -> np.ndarray:
        """Where the simulated person is aiming at time t (no state change)."""
        start = np.array(self.start_pos)
        d = self._reach_vector()
        tau = t - self._intent_t0
        if self._intent == "out":
            return start + min_jerk(0.0, PATIENT_OVERSHOOT, PATIENT_REACH_S, tau) * d
        if self._intent == "dwell":
            return start + self._s_from * d
        if self._intent == "back":
            return start + min_jerk(self._s_from, 0.0, PATIENT_REACH_S, tau) * d
        return start

    def _update_intent(self) -> None:
        s = self._progress(self._pos)
        tau = self._t - self._intent_t0
        timed_out = tau >= PATIENT_PHASE_TIMEOUT_S
        near_start = abs(s) * float(self.reach_m) <= PATIENT_NEAR_START_M

        nxt = None
        if self._intent == "rest":
            if near_start:
                if self._near_start_since is None:
                    self._near_start_since = self._t
            else:
                self._near_start_since = None
            rested = (self._near_start_since is not None
                      and self._t - self._near_start_since >= PATIENT_REST_S)
            if not self._cued and (rested or timed_out):  # engine-driven: wait for the cue
                nxt = "out"
        elif self._intent == "out":
            if s >= PATIENT_END_PROGRESS or timed_out:
                # arrived: settle at the end; gave up: stay where the hand is
                self._s_from = 1.0 if s >= PATIENT_END_PROGRESS else float(np.clip(s, 0.0, 1.0))
                nxt = "dwell"
        elif self._intent == "dwell":
            if tau >= PATIENT_DWELL_S:
                nxt = "back"
        elif self._intent == "back":
            if (tau >= PATIENT_REACH_S and near_start) or timed_out:
                nxt = "rest"
        if nxt is not None:
            self._set_intent(nxt)

    def _person_force(self, t: float, pos: np.ndarray, vel: np.ndarray) -> np.ndarray:
        """Force the person applies to the handle: effort plus passive limb load."""
        if not self.patient.present:
            return np.zeros(3)
        f = np.asarray(self.patient.effort(t, pos, vel, self._goal(t)), dtype=float)
        passive = -PASSIVE_DRAG_NS_M * vel
        passive[2] -= PASSIVE_LOAD_N
        return f + passive

    def _advance(self, dt: float) -> None:
        """Integrate dt seconds. Caller holds the lock."""
        n = max(1, math.ceil(dt / MAX_SUBSTEP_S - 1e-9))
        h = dt / n
        for _ in range(n):
            if self._k_pending is not None and self._t >= self._k_pending[1]:
                was_hold = self._at_hold_stiffness()
                self._k = self._k_pending[0]
                self._k_pending = None
                if was_hold and not self._at_hold_stiffness():
                    self._cue_reach()
            self._update_intent()
            if self._mode in ("compliant", "hold"):
                f = (self._k * (self._target - self._pos)
                     + self._person_force(self._t, self._pos, self._vel)
                     - HAND_DAMPING_NS_M * self._vel)
                self._vel = self._vel + (f / HAND_MASS_KG) * h
                self._pos = self._pos + self._vel * h
            else:  # idle (before compliance or after stop): the robot holds the hand still
                self._vel = np.zeros(3)
            self._t += h
            if (self._mode == "compliant"
                    and self._t - self._last_target_t > self.limits.watchdog_s):
                self._trip(f"watchdog: no set_target for {self._t - self._last_target_t:.2f} s")
