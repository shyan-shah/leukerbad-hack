"""Row and Strength test on the band engine (software/simple.py), built from the pieces Push uses.

Both classes subclass ``BandEngine`` and keep its interface (``start``, ``stop``, ``snapshot``,
``on_sample``, ``on_rep``, ``set_level``), its prepare (hands-off countdown, zero, empty-handle check),
its return to the start at ``stop()``, its guards (``GATE_FORCE_N``, ``GATE_SPEED``, ``HOME_ABORT_N``),
its tool-axis stiffness mapping (``_k_vector``) and every constant. Push itself is not changed.
Default arm limits only: ``set_test_limits`` is never called.

RowEngine (ids row_1 .. row_4, the levels of ``simple.LEVELS``)
- Start: Push's prepare at the start pose, then a 3 s "hands off" countdown, then ONE slow move
  (``arm.move_to``: the ramp ``arm.home()`` uses, 0.05 m/s at nominal stiffness) to the far end,
  ``FAR_M`` (0.28 m) along the reach. Then a short countdown, a second zero at the far end, the
  empty-handle check, and the band.
- The band is Push's law with the origin at the far end and the direction turned round: "out" is
  towards the patient, the band pulls back to the far end. Nothing in the law is rewritten: the
  engine's origin (``_start``) and ``sign`` are swapped once and Push's tick does the rest, so rep
  counting, "Turn back", over-travel, the anchor walk and the let-go rule are Push's own.
- ``stop()``: Push's countdown and wait rules, then one slow move back to the START pose.
- The state's ``path_start`` is the far end and ``path_end`` lies 0.30 m from it towards the patient.

StrengthEngine (id "strength", no levels)
- Push's prepare, then the handle is held at the start pose with 600 N/m along the reach (K_WALL
  across), commanded once.
- Three tries: 3 s "Get ready", 3 s "Push and hold" (phase "out"), 5 s "Rest". One RepResult per try,
  mode "isometric": peak and mean force along the reach (above the empty-handle baseline, capped at
  ``FORCE_CAP_N``), ``rom_m`` = how far the handle gave, ``completed`` = peak over 5 N.
- Ease-off: a handle pushed further than 4.5 cm ends the try (beyond 5 cm the arm's own target clamp
  lets the hold give way, so nothing more can be measured). The hold itself is not dropped.
- Release: when the handle speeds up towards the start past ``V_SNAP`` (Push's let-go test), or the
  hand's force falls 9 N below the spring's pull, the target moves up to the handle until the spring
  pulls no harder than the hand still pushes (all the way onto the handle for a hand that has gone).
  It is then walked back to the start at ``V_RETURN``.

All numbers are team-chosen, not clinical prescriptions. With a SimArm the data is simulated.
Sim and mock only so far: nothing in this file has run on the real arm.
"""
from __future__ import annotations

import math
import re

import numpy as np

from server.contract import RepResult

from .simple import (BASELINE_N, COUNTDOWN_S, DT, FORCE_CAP_N, GATE_FORCE_N, GATE_SPEED, LEAD_M, LEVELS,
                     MAX_BASELINE_N, REACH_M, V_RETURN, V_SNAP, BandEngine, _tup3)

__all__ = ["RowEngine", "StrengthEngine", "ROW_IDS", "STRENGTH_ID", "FAR_M", "row_level", "engine_class"]

ROW_IDS = tuple(f"row_{n}" for n in LEVELS)
STRENGTH_ID = "strength"

FAR_M = 0.28                 # m along the reach from the start pose: where a row begins
REZERO_COUNT_S = 2.0         # s, the second "hands off" countdown, at the far end
MOVE_TOL_M = 0.02            # m: a move that ends further than this from its goal did not arrive

TRIES = 3
READY_S = 3.0                # s "Get ready"
PUSH_S = 3.0                 # s "Push and hold"
REST_S = 5.0                 # s "Rest"
K_TEST = 600.0               # N/m along the reach during the strength test (the arm's default k_max)
EASE_M = 0.045               # m: a handle pushed further than this ends the try
MIN_PEAK_N = 5.0             # N: a try with a smaller peak is recorded as not completed
MOVING_READ_N = 7.0          # N: what the reading of a moving handle can be above the hand's force (measured: 3 to 7 N)
RELEASE_MARGIN_N = 9.0       # N: a hand force this far under the spring's pull is a let-go (twice the 4.5 N friction)
EASED_MSG = "Eased off: that's the most this arm measures."


def row_level(exercise: str) -> int | None:
    """Level of a row id ("row_3" -> 3), else None."""
    m = re.fullmatch(r"row_(\d)", str(exercise))
    n = int(m.group(1)) if m else None
    return n if n in LEVELS else None


def engine_class(exercise: str):
    """The engine class for a band-engine id (push_n, row_n, strength), else None."""
    from .simple import is_band
    if is_band(exercise):
        return BandEngine
    if row_level(exercise) is not None:
        return RowEngine
    return StrengthEngine if exercise == STRENGTH_ID else None


class _Moves:
    """A guarded ``arm.move_to``: Push's ``_home_guarded`` for a goal other than the start pose."""

    def _sim_patient(self):
        return getattr(self.arm, "patient", None) if hasattr(self.arm, "reach_m") else None

    def _move_guarded(self, goal) -> None:
        """Slow move of the empty handle to ``goal`` with ``_homing`` set, so that ``_watch_home`` holds the
        arm if the reading changes by more than HOME_ABORT_N. Raises if the move did not arrive."""
        if not hasattr(self.arm, "move_to"):
            raise RuntimeError("this arm cannot move the handle to another point (no move_to)")
        goal = _tup3(goal)
        self._home_f0 = np.asarray(self.arm.get_state().force, dtype=float)
        self._homing = True
        try:
            self.arm.move_to(goal)                    # blocks on the real arm and on a real-time SimArm
            if not getattr(self.arm, "realtime", True):
                # SimArm(realtime=False): move_to returned at once; carry the handle here, watching it
                while getattr(self.arm, "moving", False):
                    st = self.arm.get_state()
                    self._watch_home(st)
                    self._emit(st, st.pos, "idle", -1, np.asarray(st.force, dtype=float) - self.force_baseline)
                    self.arm.step(DT)
        finally:
            self._homing = False
        off = math.dist(self.arm.get_state().pos, goal)
        if off > MOVE_TOL_M:
            raise RuntimeError(f"the move ended {off * 100:.1f} cm short: something was on the handle")


class RowEngine(_Moves, BandEngine):
    GROUP = "row"

    def __init__(self, arm, session_id: str, patient_id: str, simulated: bool, *, exercise: str = "row_1",
                 level: int | None = None, **kw) -> None:
        """``exercise``: "row_1" .. "row_4" (``level`` given overrides the id's level). Everything else as
        ``BandEngine``."""
        lv = level if level is not None else row_level(exercise)
        if lv not in LEVELS:
            raise ValueError(f"exercise must be one of {', '.join(ROW_IDS)} (got {exercise!r}, level {level!r})")
        super().__init__(arm, session_id, patient_id, simulated, level=lv, **kw)
        self._sign0 = self.sign               # the reach direction (away from the patient)
        self._home = np.zeros(3)              # the start pose
        self._far = np.zeros(3)               # the far end: the band's origin
        self._at_far = False                  # the move to the far end and the second zero are done
        self._row_error: str | None = None

    # ------------------------------------------------------------------ interface
    def start(self) -> None:
        ref = self._start_ref()
        self._home = np.asarray(ref if ref is not None else self.arm.get_state().pos, dtype=float)
        self._far = self._home.copy()
        self._far[self.axis] += self._sign0 * FAR_M
        super().start()

    def snapshot(self) -> dict:
        d = super().snapshot()
        end = self._far.copy()
        end[self.axis] -= self._sign0 * REACH_M          # 0.30 m from the far end, towards the patient
        return d | {"path_start": list(_tup3(self._far)), "path_end": list(_tup3(end))}

    # ------------------------------------------------------------------ start: prepare, far end, zero again
    def _begin_band(self) -> None:
        """Called by Push's start-up when its prepare is done. First time: the empty-handle check at the
        start pose, then on to the move. Second time (at the far end): Push's own start of the band, with
        the far end as the origin and the direction turned round."""
        if not self._at_far:
            patient = self._sim_patient()
            if patient is not None:
                patient.present = False          # the simulated person follows the procedure: hands off
            if self.prepare and hasattr(self.arm, "zero_force"):
                self._check_empty()
            self._stage, self._count_end = "far_count", None
            return
        super()._begin_band()                    # baseline, compliance on, the ONE stiffness command
        self._start = self._far.copy()
        self.sign = -self._sign0
        s0 = self.sign * float(np.asarray(self.arm.get_state().pos, dtype=float)[self.axis] - self._start[self.axis])
        self._s_filt, self._anchor = s0, max(0.0, s0)
        if hasattr(self.arm, "patient") and hasattr(self.arm, "cue"):
            self.arm.reach_sign = int(self.sign)
            self.arm.reach_origin = _tup3(self._far)
            self.arm.cue("rest")

    def _check_empty(self) -> None:
        """Push's empty-handle check (mean of BASELINE_N readings under MAX_BASELINE_N), here at the start
        pose before the arm moves by itself."""
        readings = [np.asarray(self.arm.get_state().force, dtype=float) for _ in range(BASELINE_N)]
        mag = float(np.linalg.norm(np.mean(readings, axis=0)))
        if mag > MAX_BASELINE_N:
            raise RuntimeError(f"the handle reads {mag:.1f} N with nobody meant to be touching it (limit "
                               f"{MAX_BASELINE_N:.0f} N). Hands off, then start again.")

    def _tick(self) -> None:
        fn = {"far_count": self._tick_far_count, "far_move": self._tick_far_move,
              "far_zero_count": self._tick_far_zero_count, "far_zero": self._tick_far_zero}.get(self._stage)
        if fn is None:
            return super()._tick()
        fn(self.arm.get_state())

    def _hands_off(self, st, seconds: float, text: str) -> bool:
        """One tick of a "hands off" countdown that starts again while the handle moves or reads over
        GATE_FORCE_N. True when it has run out."""
        t = float(st.t)
        if self._count_end is None:
            self._count_end = t + seconds
        if float(np.linalg.norm(st.vel)) > GATE_SPEED or float(np.linalg.norm(st.force)) > GATE_FORCE_N:
            self._count_end = t + seconds        # the arm is about to act by itself: never with a hand on it
        left = max(0.0, self._count_end - t)
        with self._lock:
            self._countdown = round(left, 1)
            self._message = f"{text} {math.ceil(left - 0.005)}"
        self._emit(st, st.pos, "idle", -1, st.force)
        if left > 0.0:
            return False
        self._count_end = None
        with self._lock:
            self._countdown = None
        return True

    def _fail(self, st, err) -> None:
        self._stage = "error"
        self._say(f"Not started: {str(err).rstrip('.')}. Stop the session and start again.")
        self._emit(st, st.pos, "idle", -1, st.force)

    def _tick_far_count(self, st) -> None:
        if self._hands_off(st, COUNTDOWN_S, "Hands off: moving to the start position in"):
            self._say("The arm is moving to the start position. Hands off.")
            self._stage = "far_move"
            self._run_job(lambda: self._move_guarded(self._far))

    def _tick_far_move(self, st) -> None:
        if self._job is not None and self._job.is_alive():
            self._watch_home(st)
            return self._emit(st, st.pos, "idle", -1, st.force)
        self._job = None
        if self._job_exc is not None:
            return self._fail(st, self._job_exc)
        self._stage = "far_zero_count"
        self._tick_far_zero_count(st)

    def _tick_far_zero_count(self, st) -> None:
        if self._hands_off(st, REZERO_COUNT_S, "Hands off: zeroing in"):
            self._say("Zeroing. Hands off.")
            self._stage = "far_zero"
            self._run_job(self.arm.zero_force)

    def _tick_far_zero(self, st) -> None:
        if self._job is not None and self._job.is_alive():
            return self._emit(st, st.pos, "idle", -1, st.force)
        self._job = None
        err = self._job_exc
        if err is None:
            self._at_far = True
            try:
                return self._begin_band()
            except RuntimeError as e:
                err = e
        self._fail(st, err)

    # ------------------------------------------------------------------ back to the START pose at stop()
    def _home_guarded(self) -> None:
        """Push's guarded move to the start. Once the band has run from the far end it is ``arm.move_to``
        to the start pose (the same ramp as ``arm.home()``), so a simulated arm shows the move too."""
        if self._at_far and hasattr(self.arm, "move_to"):
            return self._move_guarded(self._home)
        super()._home_guarded()


class StrengthEngine(BandEngine):
    GROUP = "strength"

    def __init__(self, arm, session_id: str, patient_id: str, simulated: bool, *, exercise: str = STRENGTH_ID,
                 level: int | None = None, reps: int | None = None, **kw) -> None:
        """``exercise`` must be "strength". ``reps`` is the number of tries (default 3). No levels."""
        if exercise != STRENGTH_ID:
            raise ValueError(f"exercise must be {STRENGTH_ID!r}, got {exercise!r}")
        super().__init__(arm, session_id, patient_id, simulated, level=min(LEVELS), reps=reps or TRIES, **kw)
        self.exercise = STRENGTH_ID
        self._k_now = K_TEST                     # the ONE stiffness command of the session (see _begin_band)
        self._seg = "ready"                      # "ready" | "push" | "rest" | "done"
        self._seg_end: float | None = None
        self._try: dict | None = None
        self._eased = False
        self._best: float | None = None
        self._last: float | None = None

    # ------------------------------------------------------------------ interface
    def set_level(self, level: int) -> None:
        raise ValueError("this exercise has no levels")

    def snapshot(self) -> dict:
        d = super().snapshot()
        with self._lock:
            return d | {"exercise": STRENGTH_ID, "kind": "test", "level": None, "level_force_n": None,
                        "try": min(self.rep_count + 1, self.reps_target), "tries": self.reps_target,
                        "best_force_n": self._best, "last_force_n": self._last, "segment": self._seg}

    def _begin_band(self) -> None:
        super()._begin_band()
        self._seg, self._seg_end, self._try, self._eased = "ready", None, None, False
        self._anchor = 0.0

    # ------------------------------------------------------------------ the tick
    def _tick_band(self, st) -> None:
        t = float(st.t)
        dt = DT if self._last_t is None else float(np.clip(t - self._last_t, 0.0, 0.1))
        self._last_t = t
        pos = np.asarray(st.pos, dtype=float)
        force = np.asarray(st.force, dtype=float) - self.force_baseline
        a = self.axis
        if st.mode != "compliant":
            # tripped, held or faulted: never command, never re-arm. A try in progress is dropped.
            with self._lock:
                self._phase, self._try, self._band_force = "idle", None, 0.0
                self._message = (f"The arm has stopped ({st.fault or st.mode}). Let go. "
                                 "Stop the session and start again.")
                self._countdown = None
            return self._emit(st, st.pos, "idle", -1, force)

        s = self.sign * float(pos[a] - self._start[a])           # m along the reach, + = pushed out
        f_along = self.sign * float(force[a])                    # N along the reach, + = pushing out
        side = 1.0 if s >= 0 else -1.0
        m = abs(s)                                               # m the handle has given, either way
        v_back = -side * self.sign * float(st.vel[a])            # m/s towards the start

        # The hold: the target stays on the start. A release is Push's let-go rule (speeding up towards the
        # start past V_SNAP puts the target on the handle, which is then walked back at V_RETURN), plus one
        # rule Push does not need: a hand force RELEASE_MARGIN_N under the spring's pull means the hand is
        # going (held still, the two differ by the friction at most). The target then moves towards the
        # handle just far enough for the spring to match what the hand still pushes with, so the handle is
        # neither thrown back nor, under a hand that is still pushing, let go forwards.
        v_eff = v_back + max(0.0, v_back - self._v_prev)
        self._v_prev = v_back
        self._anchor = max(0.0, self._anchor - V_RETURN * dt)
        spring = self._k_now * min(LEAD_M, max(0.0, m - self._anchor))     # the arm clamps the stretch to 5 cm
        f_hand = max(0.0, side * f_along)
        if v_eff > V_SNAP:
            # Push puts the target on the handle here. Under a hand that is only easing off that would let the
            # handle jump forwards, so the spring is left what the hand still pushes with. A moving handle
            # reads up to MOVING_READ_N too much, so that much is taken off first.
            self._anchor = max(self._anchor, m - max(0.0, f_hand - MOVING_READ_N) / self._k_now)
        elif f_hand < spring - RELEASE_MARGIN_N:
            self._anchor = max(self._anchor, m - f_hand / self._k_now)      # the spring now pulls as hard as the hand pushes

        # the three segments of a try
        if self._seg_end is None:
            self._seg_end = t + READY_S
        eased_now = False
        if self._seg == "ready" and t >= self._seg_end:
            self._seg, self._seg_end = "push", t + PUSH_S
            self._try = {"t0": t, "t_s": float(st.t) - (self._t0 or float(st.t)), "f": [], "m": 0.0, "lat": []}
            self._eased = False
        if self._seg == "push":
            r = self._try
            r["f"].append(min(f_along, FORCE_CAP_N))
            r["m"] = max(r["m"], m)
            r["lat"].append(float(np.linalg.norm(np.delete(pos - self._start, a))))
            # Past EASE_M the try ends. The hold is NOT dropped: under a hand that is still pushing the handle
            # would lurch. Past 5 cm the arm's own clamp makes it a constant pull that gives way by itself.
            eased_now = m > EASE_M
            if eased_now or t >= self._seg_end:
                self._finish_try(t, eased_now)
        elif self._seg == "rest" and t >= self._seg_end:
            self._seg, self._seg_end = ("done", None) if self.done else ("ready", t + READY_S)
            self._eased = False

        self._anchor = max(0.0, min(self._anchor, m))            # never beyond the hand
        target = self._start.copy()
        target[a] += self.sign * side * self._anchor
        self.arm.set_target(_tup3(target))
        self._band_force = self._k_now * min(LEAD_M, max(0.0, m - self._anchor))

        left = None if self._seg_end is None else max(0.0, self._seg_end - t)
        n = math.ceil((left or 0.0) - 0.005)
        if self._seg == "ready":
            msg = f"Get ready: {max(n, 1)}"
        elif self._seg == "push":
            msg = "Push and hold"
        elif self._seg == "rest":
            msg = EASED_MSG if self._eased else "Rest"
        else:
            msg = "Set finished"
        self._phase = "out" if self._seg == "push" else "idle"
        self._over = m > EASE_M
        with self._lock:
            self._message = msg
            self._countdown = None if left is None else round(left, 1)
        self._emit(st, target, self._phase, self.rep_count if self._seg == "push" else -1, force)
        self._sim_cue(s, t)

    def _finish_try(self, t: float, eased: bool) -> None:
        r, self._try = self._try, None
        f = np.asarray(r["f"], dtype=float)
        peak = round(float(np.max(f)), 2)
        rep = RepResult(
            session_id=self.session_id, idx=self.rep_count, mode="isometric", dial=0.0,
            t_start=round(r["t_s"], 2), duration_s=round(t - r["t0"], 2), rom_m=round(float(r["m"]), 4),
            path_err_mean_m=round(float(np.mean(r["lat"])), 4), path_err_max_m=round(float(np.max(r["lat"])), 4),
            sparc=0.0, peak_force_n=peak, mean_force_n=round(float(np.mean(f)), 2), contribution=1.0,
            completed=bool(peak > MIN_PEAK_N), simulated=self.simulated, rescued=False)
        with self._lock:
            self.rep_count += 1
            self.reps.append(rep)
            self._last = peak
            self._best = peak if self._best is None else max(self._best, peak)
        self._seg, self._seg_end, self._eased = "rest", t + REST_S, eased
        if self.on_rep is not None:
            self.on_rep(rep)

    def _sim_cue(self, s: float, t: float) -> None:
        """A simulated patient (software.sim_arm) pushes during "Push and hold" and relaxes after it."""
        if not (hasattr(self.arm, "patient") and hasattr(self.arm, "cue")) or not getattr(self.arm, "sim_cues", True):
            return
        want = "out" if self._seg == "push" else "rest"
        if getattr(self, "_sim_intent", None) != want:
            self._sim_intent = want
            self.arm.cue(want)
